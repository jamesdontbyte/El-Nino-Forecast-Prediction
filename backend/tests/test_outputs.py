import json

import pandas as pd
import pytest

from app.layer1_forecast.outputs import (
    build_outputs,
    climatology_rows,
    climatology_years,
    confidence_band,
    duration_text,
)


def observed_table(oni_values, start="2020-01"):
    dates = pd.date_range(start, periods=len(oni_values), freq="MS")
    return pd.DataFrame({"date": dates, "oni": oni_values})


def band_from_edges(observed, oni, lower, upper):
    """Forecast band for the 6 months after the last observed month."""
    months = pd.date_range(observed["date"].iloc[-1], periods=7, freq="MS")[1:]
    return pd.DataFrame({"month": months, "oni": oni, "lower": lower, "upper": upper})


# 12 neutral months, then 6 observed El Nino months reaching the newest month.
UNDERWAY = observed_table([0.0] * 12 + [0.6, 0.9, 1.2, 1.5, 1.7, 1.8])
NEUTRAL = observed_table([0.0] * 18)


def test_confidence_band_adds_and_subtracts_rmse():
    band = confidence_band(pd.Timestamp("2026-09-01"), [1.0] * 6, {h: 0.1 * h for h in range(1, 7)})
    assert band["month"].iloc[0] == pd.Timestamp("2026-10-01")
    assert band["month"].iloc[-1] == pd.Timestamp("2027-03-01")
    assert band["lower"].tolist() == pytest.approx([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
    assert band["upper"].tolist() == pytest.approx([1.1, 1.2, 1.3, 1.4, 1.5, 1.6])


def test_underway_and_ending_gives_a_low_to_high_range():
    band = band_from_edges(
        UNDERWAY,
        oni=[1.6, 1.2, 0.8, 0.4, 0.1, 0.0],
        lower=[1.4, 0.4, 0.2, 0.0, -0.3, -0.5],  # warm for 1 month
        upper=[1.8, 1.6, 1.4, 0.6, 0.4, 0.3],  # warm for 4 months
    )
    out = build_outputs(UNDERWAY, band, "test")

    assert out["event_underway"] is True
    assert out["start_month"] == "2021-01"
    assert out["duration_months"] == {"low": 7, "high": 10, "text": "from 7 to 10 months"}
    assert out["duration_open_ended"] is False


def test_underway_and_open_ended():
    band = band_from_edges(
        UNDERWAY,
        oni=[2.0] * 6,
        lower=[1.5, 1.0, 0.4, 0.2, 0.0, 0.0],  # warm for 2 months
        upper=[2.5, 2.4, 2.3, 2.2, 2.1, 2.0],  # warm for all 6
    )
    out = build_outputs(UNDERWAY, band, "test")

    assert out["duration_open_ended"] is True
    assert out["duration_months"] == {"low": 8, "high": 12, "text": "from 8 months to at least 12 months"}


def test_both_edges_warm_all_six_months_gives_at_least_n():
    band = band_from_edges(UNDERWAY, oni=[2.0] * 6, lower=[1.0] * 6, upper=[3.0] * 6)
    out = build_outputs(UNDERWAY, band, "test")

    assert out["duration_open_ended"] is True
    assert out["duration_months"] == {"low": 12, "high": 12, "text": "at least 12 months"}


def test_upper_edge_dips_then_recovers_is_not_open_ended():
    band = band_from_edges(
        UNDERWAY,
        oni=[1.5, 1.0, 0.3, 0.6, 0.9, 1.2],
        lower=[1.2, 0.6, 0.0, 0.2, 0.5, 0.8],
        upper=[1.8, 1.4, 0.4, 1.0, 1.3, 1.6],  # dips below +0.5 at lead 3, warm again at 6
    )
    out = build_outputs(UNDERWAY, band, "test")

    assert out["duration_open_ended"] is False
    assert out["duration_months"]["high"] == 6 + 2  # the run stops at the first dip
    assert out["duration_months"]["low"] == 6 + 2


def test_underway_strength_uses_observed_and_forecast_peak():
    band = band_from_edges(UNDERWAY, oni=[2.2, 1.0, 0.0, 0.0, 0.0, 0.0], lower=[0.0] * 6, upper=[3.0] * 6)
    assert build_outputs(UNDERWAY, band, "test")["strength"] == "strong"  # observed peak 1.8, forecast 2.2

    weak = observed_table([0.0] * 12 + [0.6, 0.7, 0.8, 0.7, 0.6, 0.6])
    band = band_from_edges(weak, oni=[1.2, 0.9, 0.0, 0.0, 0.0, 0.0], lower=[0.0] * 6, upper=[1.0] * 6)
    assert build_outputs(weak, band, "test")["strength"] == "moderate"  # forecast pushes the peak to 1.2


def test_predicted_event_can_start_in_the_observed_tail():
    observed = observed_table([0.0] * 15 + [0.6, 0.7, 0.8])  # 3 warm months: not an event yet
    band = band_from_edges(observed, oni=[1.0, 1.1, 0.9, 0.3, 0.0, 0.0], lower=[0.0] * 6, upper=[1.0] * 6)
    out = build_outputs(observed, band, "test")

    assert out["event_underway"] is False
    assert out["start_month"] == "2021-04"  # first observed warm month
    assert out["strength"] == "moderate"
    assert out["duration_months"] is None
    assert out["duration_open_ended"] is False


def test_late_warming_too_short_to_count_gives_no_start():
    band = band_from_edges(NEUTRAL, oni=[0.0, 0.1, 0.2, 0.6, 0.8, 1.0], lower=[0.0] * 6, upper=[1.0] * 6)
    out = build_outputs(NEUTRAL, band, "test")

    assert out["start_month"] is None
    assert out["strength"] is None
    assert out["event_status"] == ["Neutral", "Neutral", "Neutral", "El Nino", "El Nino", "El Nino"]


def test_no_event_and_output_is_json_ready():
    band = band_from_edges(NEUTRAL, oni=[0.0] * 6, lower=[-0.5] * 6, upper=[0.5] * 6)
    out = build_outputs(NEUTRAL, band, "test_model")

    assert out["event_underway"] is False
    assert out["start_month"] is None
    assert out["duration_months"] is None
    assert out["model_used"] == "test_model"
    assert out["forecast_series"][0] == {"month": "2021-07", "oni": 0.0, "lower": -0.5, "upper": 0.5}
    json.dumps(out)  # fails if any value is not plain JSON (for the API later)


@pytest.mark.parametrize(
    ("low", "high", "open_ended", "expected"),
    [
        (7, 10, False, "from 7 to 10 months"),
        (8, 8, False, "8 months"),
        (8, 12, True, "from 8 months to at least 12 months"),
        (12, 12, True, "at least 12 months"),
    ],
)
def test_duration_text(low, high, open_ended, expected):
    assert duration_text(low, high, open_ended) == expected


# Four full years (2000 to 2003) plus 3 months of 2004.
# 2001 has an El Nino event from November 2001 to March 2002 (5 months, crossing the year end).
# 2003 is La Nina all year. The 2004 months are strongly warm but must be ignored.
CLIMATOLOGY = observed_table(
    [0.0] * 12
    + [0.0] * 10 + [0.6, 0.8]
    + [0.9, 0.7, 0.6] + [0.0] * 9
    + [-1.0] * 12
    + [2.5] * 3,
    start="2000-01",
)


def test_climatology_uses_full_years_only():
    assert climatology_years(CLIMATOLOGY) == (2000, 2003)


def test_climatology_has_12_rows_and_shares_sum_to_one():
    rows = climatology_rows(CLIMATOLOGY)

    assert [row["month"] for row in rows] == list(range(1, 13))
    for row in rows:
        total = row["el_nino_share"] + row["neutral_share"] + row["la_nina_share"]
        assert total == pytest.approx(1.0)
    json.dumps(rows)


def test_climatology_ignores_the_incomplete_newest_year():
    january = climatology_rows(CLIMATOLOGY)[0]

    # Without 2004: Jan is neutral in 2000, El Nino in 2002, La Nina in 2003, neutral in 2001.
    assert january["el_nino_share"] == 0.25
    assert january["la_nina_share"] == 0.25
    assert january["neutral_share"] == 0.5
    assert january["mean_oni"] == round((0.0 + 0.0 + 0.9 - 1.0) / 4, 2)


def test_climatology_counts_event_start_in_its_start_month():
    rows = climatology_rows(CLIMATOLOGY)

    assert rows[10]["event_start_share"] == 0.25  # November, one start in 4 years
    assert sum(row["event_start_share"] for row in rows) == 0.25
