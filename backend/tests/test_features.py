import pandas as pd

from app.layer1_forecast.features import (
    LAG_COLUMNS,
    TARGET_COLUMNS,
    build_features,
    split_by_date,
)


def make_counting_table(start="2000-01", months=40):
    """Made-up table where ONI equals the row number, so every shift is easy to check."""
    dates = pd.date_range(start, periods=months, freq="MS")
    return pd.DataFrame({"date": dates, "oni": [float(i) for i in range(months)]})


def test_lags_and_targets_line_up():
    frame = build_features(make_counting_table())
    row = frame[frame["date"] == pd.Timestamp("2001-06-01")].iloc[0]
    anchor = 17  # 2001-06 is row 17 of the made-up table

    assert row["oni_lag1"] == anchor  # newest published value
    assert row["oni_lag3"] == anchor - 2
    assert row["oni_lag6"] == anchor - 5
    assert row["oni_lag12"] == anchor - 11
    for h in range(1, 7):
        assert row[f"target_lead{h}"] == anchor + h


def test_features_never_use_months_after_the_anchor():
    frame = build_features(make_counting_table())
    anchor_value = frame["oni_lag1"]  # equals the anchor's row number
    for column in LAG_COLUMNS:
        assert (frame[column] <= anchor_value).all()


def test_rows_without_full_lag_history_are_dropped():
    frame = build_features(make_counting_table())
    assert frame["date"].min() == pd.Timestamp("2000-12-01")  # lag 12 needs 11 earlier months
    assert frame[LAG_COLUMNS].notna().all().all()


def test_latest_row_is_kept_with_empty_targets():
    table = make_counting_table()
    frame = build_features(table)
    latest = frame.iloc[-1]

    assert latest["date"] == table["date"].iloc[-1]
    assert latest[TARGET_COLUMNS].isna().all()


def test_split_keeps_targets_inside_each_period():
    table = make_counting_table(start="2006-01", months=150)  # 2006-01 to 2018-06
    splits = split_by_date(build_features(table))
    furthest_target = {name: part["date"] + pd.DateOffset(months=6) for name, part in splits.items()}

    assert splits["train"]["date"].max() == pd.Timestamp("2008-06-01")
    assert furthest_target["train"].max() <= pd.Timestamp("2008-12-01")
    assert splits["validation"]["date"].min() == pd.Timestamp("2009-01-01")
    assert splits["validation"]["date"].max() == pd.Timestamp("2016-06-01")
    assert furthest_target["validation"].max() <= pd.Timestamp("2016-12-01")
    assert splits["test"]["date"].min() == pd.Timestamp("2017-01-01")


def test_no_month_is_in_two_splits():
    table = make_counting_table(start="2006-01", months=150)
    splits = split_by_date(build_features(table))
    all_dates = pd.concat([part["date"] for part in splits.values()])
    assert not all_dates.duplicated().any()
