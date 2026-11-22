import pandas as pd
import pytest

from app.layer1_forecast.labels import (
    ENSO_MONTHLY_PATH,
    find_events,
    month_status,
    strength_from_peak,
)


def make_table(oni_values, start="2000-01"):
    """Small made-up monthly ONI table for tests."""
    dates = pd.date_range(start, periods=len(oni_values), freq="MS")
    return pd.DataFrame({"date": dates, "oni": oni_values})


def test_month_status_at_thresholds():
    oni = pd.Series([0.5, 0.49, 0.0, -0.49, -0.5, 2.0, -2.0])
    expected = ["El Nino", "Neutral", "Neutral", "Neutral", "La Nina", "El Nino", "La Nina"]
    assert month_status(oni).tolist() == expected


@pytest.mark.parametrize(
    ("peak", "expected"),
    [(0.5, "weak"), (0.99, "weak"), (1.0, "moderate"), (1.49, "moderate"), (1.5, "strong"), (2.6, "strong")],
)
def test_strength_cutoffs(peak, expected):
    assert strength_from_peak(peak) == expected


def test_four_warm_months_is_not_an_event():
    table = make_table([0.0, 0.6, 0.7, 0.8, 0.6, 0.0])
    assert find_events(table).empty


def test_five_warm_months_is_an_event():
    table = make_table([0.0, 0.6, 0.9, 1.2, 0.8, 0.5, 0.2])
    events = find_events(table)

    assert len(events) == 1
    event = events.iloc[0]
    assert event["start_month"] == pd.Timestamp("2000-02-01")
    assert event["end_month"] == pd.Timestamp("2000-06-01")
    assert event["duration_months"] == 5
    assert event["peak_oni"] == 1.2
    assert event["peak_month"] == pd.Timestamp("2000-04-01")
    assert event["strength"] == "moderate"
    assert not event["ongoing"]


def test_a_dip_below_threshold_splits_events():
    table = make_table([0.6] * 5 + [0.4] + [0.7] * 5 + [0.0])
    events = find_events(table)
    assert events["duration_months"].tolist() == [5, 5]


def test_event_at_end_of_data_is_ongoing():
    table = make_table([0.0, 0.2, 0.6, 1.0, 1.6, 2.0, 2.4])
    event = find_events(table).iloc[0]

    assert event["ongoing"]
    assert pd.isna(event["end_month"])
    assert event["duration_months"] == 5
    assert event["strength"] == "strong"


def test_short_warm_spell_at_end_of_data_is_not_an_event_yet():
    table = make_table([0.0, 0.0, 0.6, 0.8])
    assert find_events(table).empty


KNOWN_EVENT_STARTS = ["1982-05", "1997-05", "2014-10", "2023-06"]  # 2015-16 run starts in late 2014


@pytest.mark.skipif(not ENSO_MONTHLY_PATH.exists(), reason="processed data not built (data/ is gitignored)")
def test_known_events_found_in_real_data():
    table = pd.read_csv(ENSO_MONTHLY_PATH, parse_dates=["date"])
    events = find_events(table)
    start_text = events["start_month"].dt.strftime("%Y-%m")

    known = events[start_text.isin(KNOWN_EVENT_STARTS)]
    assert len(known) == len(KNOWN_EVENT_STARTS)
    assert (known["strength"] == "strong").all()
    assert not known["ongoing"].any()

    latest = events.iloc[-1]
    assert latest["start_month"] == pd.Timestamp("2026-05-01")
    assert latest["ongoing"]
    assert events["ongoing"].sum() == 1
