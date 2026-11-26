import numpy as np
import pandas as pd
import pytest

from app.data.load_era5 import FEATURE_COLUMNS, RAW_COLUMNS
from app.layer1_forecast import train
from app.layer1_forecast.features import (
    LAG_AND_ERA5_COLUMNS,
    LAG_COLUMNS,
    LEADS,
    build_features,
)


def make_table(oni_values, start="2000-01"):
    dates = pd.date_range(start, periods=len(oni_values), freq="MS")
    return pd.DataFrame({"date": dates, "oni": oni_values})


def scores_table(mean_rmse_by_model):
    rows = []
    for model, rmse in mean_rmse_by_model.items():
        rows += [{"model": model, "lead": lead, "rmse": rmse} for lead in LEADS]
    return pd.DataFrame(rows)


def test_choose_best_picks_lowest_mean_rmse_and_ignores_persistence():
    scores = scores_table({"persistence": 0.1, "linear_regression": 0.5, "xgboost": 0.4, "random_forest": 0.6})
    assert train.choose_best(scores) == "xgboost"


def test_model_is_chosen_from_validation_not_test(monkeypatch):
    validation_winner = scores_table({"linear_regression": 0.3, "xgboost": 0.9, "random_forest": 0.9})
    test_winner = scores_table({"linear_regression": 0.9, "xgboost": 0.1, "random_forest": 0.9})
    calls = []

    def fake_run_validation(fit_rows, score_rows):
        calls.append(len(calls))
        regression = validation_winner if len(calls) == 1 else test_winner
        return {"regression": regression, "status": pd.DataFrame(), "confusion": {}}

    monkeypatch.setattr(train.models, "run_validation", fake_run_validation)
    t = np.arange(400)
    table = make_table(2.0 * np.sin(2 * np.pi * t / 40), start="1990-01")
    results = train.run_comparison(table)

    assert len(calls) == 2  # once for validation, once for test
    assert results["best"] == "linear_regression"


def test_rows_before_test_have_no_target_after_2016():
    frame = build_features(make_table([0.0] * 200, start="2005-01"))
    rows = train.rows_before_test(frame)
    furthest = rows["date"] + pd.DateOffset(months=6)
    assert furthest.max() == pd.Timestamp("2016-12-01")


def test_save_and_load_give_the_same_predictions(tmp_path):
    t = np.arange(200)
    frame = build_features(make_table(2.0 * np.sin(2 * np.pi * t / 40)))
    fitted = train.models.fit_per_lead(train.models.REGRESSORS["linear_regression"], frame)
    bundle = {"model_name": "linear_regression", "models": fitted, "rmse_by_lead": {h: 0.1 for h in LEADS}}

    train.save_model(bundle, {"model_name": "linear_regression"}, directory=tmp_path)
    loaded = train.load_model(directory=tmp_path)

    sample = frame[LAG_COLUMNS].iloc[:5]
    for lead in LEADS:
        assert loaded["models"][lead].predict(sample) == pytest.approx(fitted[lead].predict(sample))
    assert (tmp_path / train.METADATA_FILE).exists()


def test_month_difference():
    assert train.month_difference(pd.Timestamp("2024-02-01"), pd.Timestamp("2023-11-01")) == 3
    assert train.month_difference(pd.Timestamp("2023-11-01"), pd.Timestamp("2024-02-01")) == -3


def test_event_scores_detects_a_late_start_and_skips_ongoing_duration():
    # True series: one finished event (months 10 to 17) and one ongoing at the end (months 30 to 35).
    oni = [0.0] * 10 + [1.0] * 8 + [0.0] * 12 + [1.0] * 6
    observed = make_table(oni)
    # Lead-1 predictions: the first event starts 2 months late and lasts 6 months; the second matches.
    predicted = [0.0] * 12 + [1.0] * 6 + [0.0] * 12 + [1.0] * 6
    predictions = pd.DataFrame({
        "lead": 1,
        "target_month": observed["date"],
        "predicted": predicted,
        "actual": oni,
    })

    events = train.event_scores(observed, predictions, first_test_month="2000-01-01")

    finished, ongoing = events.iloc[0], events.iloc[1]
    assert finished["detected"]
    assert finished["start_error_months"] == 2
    assert finished["duration_error_months"] == 6 - 8
    assert ongoing["ongoing"]
    assert ongoing["detected"]
    assert pd.isna(ongoing["duration_error_months"])


def test_event_scores_uses_forecast_months_past_the_newest_observation():
    # True series: an ongoing event in the last 5 observed months (months 5 to 9).
    observed = make_table([0.0] * 5 + [1.0] * 5)
    # Lead-3 predictions run 3 months past the data. The predicted warm run (months 7 to 12)
    # has only 3 months on or before the newest observation, too short for an event on its own.
    predictions = pd.DataFrame({
        "lead": 3,
        "target_month": pd.date_range("2000-01", periods=13, freq="MS"),
        "predicted": [0.0] * 7 + [1.0] * 6,
        "actual": np.nan,
    })
    events = train.event_scores(observed, predictions, first_test_month="2000-01-01")
    assert events.iloc[0]["detected"]
    assert events.iloc[0]["start_error_months"] == 2


def test_hindcast_models_ignore_data_after_their_anchor():
    t = np.arange(240)  # 1950-01 to 1969-12
    table = make_table(2.0 * np.sin(2 * np.pi * t / 40), start="1950-01")
    before = train.fit_hindcast_models(table, "linear_regression")

    changed = table.copy()
    after_anchor = changed["date"] > train.hindcast_anchor(1962)
    changed.loc[after_anchor, "oni"] = 5.0
    after = train.fit_hindcast_models(changed, "linear_regression")

    sample = build_features(table)[LAG_COLUMNS].iloc[:5]
    for lead in LEADS:
        assert after[1962][lead].predict(sample) == pytest.approx(before[1962][lead].predict(sample))
    assert after[1963][1].predict(sample) != pytest.approx(before[1963][1].predict(sample))


def test_hindcast_years_run_to_the_year_before_the_newest_month():
    t = np.arange(240)  # 1950-01 to 1969-12
    table = make_table(2.0 * np.sin(2 * np.pi * t / 40), start="1950-01")
    assert sorted(train.fit_hindcast_models(table, "linear_regression")) == list(range(1960, 1969))


def test_hindcast_year_with_too_little_data_is_skipped():
    t = np.arange(60)  # 1959-06 to 1964-05: March 1960 has fewer than 12 months behind it
    table = make_table(2.0 * np.sin(2 * np.pi * t / 40), start="1959-06")
    assert sorted(train.fit_hindcast_models(table, "linear_regression")) == [1961, 1962, 1963]


def test_hindcast_era5_normals_use_only_earlier_years():
    dates = pd.date_range("1950-01-01", "2020-12-01", freq="MS")
    raw = pd.DataFrame({"date": dates, **{c: np.arange(len(dates), dtype=float) for c in RAW_COLUMNS}})
    before = train.hindcast_era5(raw, 1990)

    changed = raw.copy()
    changed.loc[changed["date"].dt.year >= 1990, RAW_COLUMNS] += 1000  # the hindcast year and later
    after = train.hindcast_era5(changed, 1990)

    earlier = dates.year < 1990
    assert np.allclose(before.loc[earlier, FEATURE_COLUMNS], after.loc[earlier, FEATURE_COLUMNS])


def test_hindcast_models_with_era5_use_the_era5_columns():
    t = np.arange(400)
    table = make_table(2.0 * np.sin(2 * np.pi * t / 40), start="1990-01")
    noise = np.random.default_rng(1).normal(size=(len(table), len(RAW_COLUMNS)))
    era5 = pd.DataFrame(noise, columns=RAW_COLUMNS).assign(date=table["date"])

    fitted = train.fit_hindcast_models(table, "linear_regression", era5)
    assert fitted  # at least one year
    for by_lead in fitted.values():
        assert list(by_lead[1].feature_names_in_) == LAG_AND_ERA5_COLUMNS
