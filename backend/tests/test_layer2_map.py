import math

import pandas as pd
import pytest

from app.layer2 import map_output, train
from app.layer2.features import load_lookup


def test_colour_band_edges():
    assert map_output.dryness_colour(40.0) == "red"
    assert map_output.dryness_colour(40.1) == "yellow"
    assert map_output.dryness_colour(80.0) == "yellow"
    assert map_output.dryness_colour(80.1) == "green"
    assert map_output.dryness_colour(None) == "grey"
    assert map_output.dryness_colour(float("nan")) == "grey"


def monthly(start: str, values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.date_range(start, periods=len(values), freq="MS"), "oni": values})


def test_quarter_phase_finds_el_nino_la_nina_and_neutral():
    # 2000: neutral all year. 2001: El Nino Jan-Jun (6 months). 2002: La Nina Jan-Jun.
    values = [0.0] * 12 + [1.0] * 6 + [0.0] * 6 + [-1.0] * 6 + [0.0] * 6
    phases = map_output.quarter_phase(monthly("2000-01-01", values)).set_index(["year", "quarter"])["phase"]
    assert phases[(2000, 1)] == "Neutral"
    assert phases[(2001, 1)] == "El Nino" and phases[(2001, 2)] == "El Nino"
    assert phases[(2002, 2)] == "La Nina"
    assert phases[(2002, 4)] == "Neutral"


def test_combined_oni_prefers_observed_and_crosses_the_year():
    enso = monthly("2026-07-01", [1.0, 1.0, 1.0])  # Q3 observed
    forecast = [{"month": m, "oni": 2.0} for m in
                ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"]]
    oni = map_output.combined_oni(enso, forecast).set_index(["year", "quarter"])
    assert oni.loc[(2026, 3), "oni"] == pytest.approx(1.0)  # September stays observed
    assert oni.loc[(2027, 1), "oni_prev"] == pytest.approx(2.0)  # Q1 uses last year's Q4

    quarters = map_output.forecast_quarters(enso, map_output.combined_oni(enso, forecast))
    assert quarters[["year", "quarter"]].values.tolist() == [[2026, 4], [2027, 1]]
    assert quarters["oni_prev"].iloc[0] == pytest.approx(1.0)  # Q4's last quarter is observed Q3


def test_forecast_quarter_without_last_quarter_is_an_error():
    enso = monthly("2026-08-01", [1.0, 1.0])  # Q3 incomplete, so Q4 has no last-quarter ONI
    forecast = [{"month": m, "oni": 2.0} for m in ["2026-10", "2026-11", "2026-12"]]
    with pytest.raises(ValueError):
        map_output.forecast_quarters(enso, map_output.combined_oni(enso, forecast))


def test_every_shape_once_ncr_coloured_isabela_and_sga_grey():
    lookup = load_lookup()
    rain = pd.DataFrame({"pcode": sorted(lookup["rain_pcode"].dropna().unique()), "rain_pct": 50.0})
    shapes = pd.DataFrame(map_output._shapes(lookup, rain)).set_index("map_psgc")
    assert len(shapes) == len(lookup) == 88 and shapes.index.is_unique
    ncr = shapes.loc[["1303900000", "1307400000", "1307500000", "1307600000"]]
    assert (ncr["colour"] == "yellow").all()
    assert (shapes.loc[["0990100000", "1999900000"], "colour"] == "grey").all()
    assert (shapes["colour"] == "grey").sum() == 2


def test_map_views_from_saved_models():
    paths = [train.SAVED_MODELS_DIR / train.RAIN_MODEL_FILE, train.SAVED_MODELS_DIR / "oni_forecast.joblib"]
    if not all(path.exists() for path in paths):
        pytest.skip("saved models are missing: run both train commands")
    import joblib

    saved = joblib.load(paths[0])
    assert set(saved) >= {"model_name", "model"}
    try:
        quarters = map_output.load_map_views()
    except FileNotFoundError:
        pytest.skip("data files are missing (data is gitignored)")

    assert len(quarters) >= 1
    for quarter in quarters:
        assert set(quarter["views"]) == {"prediction", "normal", "el_nino_2015_16", "el_nino_2023_24"}
        for shape in quarter["views"]["prediction"]["shapes"]:
            assert shape["rain_pct"] is None or math.isfinite(shape["rain_pct"])
