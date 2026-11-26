import numpy as np
import pandas as pd
import pytest

from app.layer2 import models
from app.layer2.features import (
    RAIN_TARGET,
    YIELD_TARGET,
    add_previous_quarter,
    el_nino_dryness,
    normal_yield,
    quarterly_oni,
    split_by_year,
    yield_change,
)
from app.layer2.train import with_predicted_rain


def test_quarterly_oni_is_the_mean_of_three_months_and_needs_all_three():
    dates = pd.date_range("2008-01-01", "2008-05-01", freq="MS")  # Q1 complete, Q2 has 2 months
    enso = pd.DataFrame({"date": dates, "oni": [0.3, 0.6, 0.9, 1.0, 1.0]})
    quarters = quarterly_oni(enso)
    assert quarters[["year", "quarter"]].values.tolist() == [[2008, 1]]
    assert quarters["oni"].iloc[0] == pytest.approx(0.6)


def test_previous_quarter_crosses_the_year_and_leaves_gaps_empty():
    table = pd.DataFrame({
        "pcode": ["A", "A", "A"], "year": [2008, 2009, 2009], "quarter": [4, 1, 3], "value": [1.0, 2.0, 3.0],
    })
    result = add_previous_quarter(table, "value", keys=["pcode"]).set_index(["year", "quarter"])
    assert result.loc[(2009, 1), "value_prev"] == 1.0  # 2009 Q1 uses 2008 Q4
    assert np.isnan(result.loc[(2009, 3), "value_prev"])  # 2009 Q2 is missing


def crop_rows(years, yields):
    return pd.DataFrame({"crop_type": "Palay", "province": "P", "quarter": 1, "year": years,
                         "yield_t_per_ha": yields})


def test_normal_uses_only_the_ten_previous_years():
    years = list(range(2000, 2013))
    crops = crop_rows(years, [float(y - 1999) for y in years])  # 1, 2, 3, ... a straight line
    crops.loc[crops["year"] == 2012, "yield_t_per_ha"] = 100.0  # the scored year must not matter
    normal = normal_yield(crops).set_axis(crops["year"])
    assert normal.loc[:2009].isna().all()  # fewer than 10 earlier years
    assert normal.loc[2010] == pytest.approx(11.0)
    assert normal.loc[2012] == pytest.approx(13.0)


def test_normal_is_empty_when_one_of_the_ten_years_is_missing():
    years = [y for y in range(2000, 2012) if y != 2005]  # 2005 has no yield
    crops = crop_rows(years, [5.0] * len(years))
    normal = normal_yield(crops).set_axis(crops["year"])
    assert np.isnan(normal.loc[2010]) and np.isnan(normal.loc[2011])


def test_yield_change_is_clipped_and_needs_a_positive_normal():
    change = yield_change(pd.Series([3.0, 0.5, 9.0, 1.0]), pd.Series([2.0, 2.0, 1.0, 0.0]))
    assert change.tolist()[:3] == [50.0, -75.0, 100.0]  # 800 percent is clipped to 100
    assert np.isnan(change.iloc[3])


def test_split_boundaries():
    splits = split_by_year(pd.DataFrame({"year": [2008, 2009, 2016, 2017]}))
    assert [part["year"].tolist() for part in splits.values()] == [[2008], [2009, 2016], [2017]]


@pytest.fixture
def rain_table():
    rng = np.random.default_rng(0)
    rows = pd.DataFrame([(p, y, q) for p in ["PH01", "PH02"] for y in range(1990, 2000) for q in range(1, 5)],
                        columns=["pcode", "year", "quarter"])
    rows["oni"] = rng.normal(size=len(rows))
    rows["oni_prev"] = rng.normal(size=len(rows))
    rows[RAIN_TARGET] = 100 - 20 * rows["oni"] + rng.normal(size=len(rows))
    return rows


def test_province_line_recovers_each_line():
    features = pd.DataFrame({"pcode": ["A"] * 4 + ["B"] * 4, "quarter": 1, "oni": [0.0, 1, 2, 3] * 2})
    target = pd.Series([100.0, 90, 80, 70, 50, 60, 70, 80])
    predicted = models.ProvinceLine().fit(features, target).predict(features)
    assert predicted == pytest.approx(target.to_numpy())


def test_every_model_fits_and_predicts(rain_table):
    yield_rows = rain_table.assign(crop_type="Palay", rain_pct=rain_table[RAIN_TARGET],
                                   rain_pct_prev=rain_table[RAIN_TARGET], **{YIELD_TARGET: rain_table["oni"]})
    for registry, table, target in [(models.RAIN_MODELS, rain_table, RAIN_TARGET),
                                    (models.YIELD_MODELS, yield_rows, YIELD_TARGET)]:
        scores, _ = models.compare(registry, table, table, target, reference=0.0)
        assert scores["rows"].nunique() == 1 and np.isfinite(scores["rmse"]).all()
        assert models.choose_best(scores, registry) in registry  # the reference never wins


def test_departure_line_predicts_zero_for_a_normal_quarter():
    rng = np.random.default_rng(0)
    rows = pd.DataFrame({"rain_pct": rng.uniform(40, 160, 50), "rain_pct_prev": rng.uniform(40, 160, 50),
                         "oni": rng.normal(0, 1, 50), "oni_prev": rng.normal(0, 1, 50)})
    target = 5.0 + (rows["rain_pct"] - 100) * 0.1  # a fixed +5 level the model must not learn
    model = models.DepartureLine().fit(rows, target)
    normal = pd.DataFrame({"rain_pct": [100.0], "rain_pct_prev": [100.0], "oni": [0.0], "oni_prev": [0.0]})
    assert model.predict(normal)[0] == pytest.approx(0.0)


def test_saved_models_load_and_predict():
    """The files written by `python -m app.layer2.train` load back and predict on real rows."""
    import joblib

    from app.layer2 import train
    from app.layer2.features import load_tables

    paths = [train.SAVED_MODELS_DIR / train.RAIN_MODEL_FILE, train.SAVED_MODELS_DIR / train.YIELD_MODEL_FILE]
    if not all(path.exists() for path in paths):
        pytest.skip("saved Layer 2 models are missing: run python -m app.layer2.train")
    try:
        tables = load_tables()
    except FileNotFoundError:
        pytest.skip("data files are missing (data is gitignored)")

    for path, table in zip(paths, [tables["rain"], tables["yield"]]):
        saved = joblib.load(path)
        predictions = saved["model"].predict(table.tail(5))
        assert len(predictions) == 5 and np.isfinite(predictions).all(), saved["model_name"]


def test_predicted_rain_replaces_observed_rain(rain_table):
    rain_model = models.RAIN_MODELS["province_line"]().fit(rain_table, rain_table[RAIN_TARGET])
    yield_rows = rain_table[rain_table["year"] == 1995].assign(rain_pct=-1.0, rain_pct_prev=-1.0)
    rows = with_predicted_rain(yield_rows, rain_table, rain_model)
    assert len(rows) == len(yield_rows) and (rows["rain_pct"] > 0).all()


def test_xgboost_rain_model_reads_oni_zero_as_zero_not_missing():
    # Rain falls steadily with ONI, so ONI 0.0 must predict close to ONI 0.001, not like a missing value.
    rng = np.random.default_rng(0)
    oni = rng.uniform(-2, 2, 2000)
    # Many provinces, as in the real data, so the one-hot columns would make the input sparse.
    rows = pd.DataFrame({"pcode": rng.choice([f"P{i}" for i in range(50)], 2000), "quarter": rng.integers(1, 5, 2000),
                         "oni": oni, "oni_prev": oni})
    model = models.RAIN_MODELS["xgboost"]().fit(rows, 100 - 20 * oni)
    at = {value: model.predict(rows.head(1).assign(oni=value, oni_prev=value))[0] for value in [0.0, 0.001]}
    assert at[0.0] == pytest.approx(at[0.001], abs=1)


def dryness_history():
    """Two provinces over 1980-1999. Strong quarters (ONI 1.5) are Q1 1983, 1990 and 1998."""
    rows = []
    for year in range(1980, 2000):
        for quarter in [1, 2, 3, 4]:
            oni = 1.5 if (year, quarter) in {(1983, 1), (1990, 1), (1998, 1)} else 0.2
            for pcode, rain in [("A", 50.0 + year - 1980), ("B", 100.0)]:
                rows.append({"pcode": pcode, "year": year, "quarter": quarter, "rain_pct_of_normal": rain, "oni": oni})
    return pd.DataFrame(rows)


def test_dryness_uses_only_strong_quarters_before_the_row_year():
    history = dryness_history()
    rows = pd.DataFrame({"pcode": ["A", "A", "A", "B", "A"], "year": [1983, 1984, 1995, 1995, 1995],
                         "quarter": [1, 1, 1, 1, 2]})
    values = el_nino_dryness(rows, history).tolist()

    assert np.isnan(values[0])  # 1983 Q1 itself is not "before 1983"
    assert values[1] == pytest.approx(53 - 76.5)  # 1983 only: A 53, country mean (53 + 100) / 2
    assert values[2] == pytest.approx(((53 - 76.5) + (60 - 80)) / 2)  # 1983 and 1990
    assert values[3] == pytest.approx(((100 - 76.5) + (100 - 80)) / 2)
    assert np.isnan(values[4])  # no strong Q2 quarter


def test_dryness_is_unchanged_by_data_from_the_row_year_on():
    history = dryness_history()
    rows = pd.DataFrame({"pcode": ["A", "B"], "year": [1995, 1995], "quarter": [1, 1]})
    before = el_nino_dryness(rows, history)

    changed = history.copy()
    later = changed["year"] >= 1995
    changed.loc[later, "rain_pct_of_normal"] += 500
    changed.loc[later, "oni"] = 2.0  # every later quarter becomes strong too
    assert el_nino_dryness(rows, changed).tolist() == pytest.approx(before.tolist())
