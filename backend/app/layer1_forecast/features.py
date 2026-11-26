"""Build lag features, lead targets, and the date split for the ONI forecast models.

Each row is anchored on month B: the newest ONI value that would be published at
forecast time (ONI is a centred three-month average, so it is about two months old).
- Lag k feature:  ONI k months before the first forecast month B+1, so lag 1 = ONI(B).
- Lead h target:  ONI at B+h.
- ERA5 lag k:     the ERA5 anomaly k-1 months before B, so lag 1 = ERA5(B) (add_era5_lags).
Every feature is at or before B, so nothing from the future leaks into the inputs.

Run from backend/:  python -m app.layer1_forecast.features   (prints the split sizes)
"""

import pandas as pd

from app.data.load_enso import OUTPUT_PATH as ENSO_MONTHLY_PATH
from app.data.load_era5 import FEATURE_COLUMNS as ERA5_COLUMNS

LAGS = [1, 3, 6, 12]
LEADS = list(range(1, 7))
LAG_COLUMNS = [f"oni_lag{k}" for k in LAGS]
TARGET_COLUMNS = [f"target_lead{h}" for h in LEADS]
ERA5_LAGS = [1, 3]
ERA5_LAG_COLUMNS = [f"{column}_lag{k}" for column in ERA5_COLUMNS for k in ERA5_LAGS]

# Split by the anchor month's year (inclusive). Test runs to the latest month.
TRAIN_LAST_YEAR = 2008
VALIDATION_LAST_YEAR = 2016


def build_features(table: pd.DataFrame) -> pd.DataFrame:
    """Return one row per anchor month B with lag features and lead targets.

    `table` needs columns `date` (first day of each month, no gaps) and `oni`.
    Rows without a full lag history are dropped. Targets that are not observed yet
    (at the end of the data) stay empty (NaN).
    """
    table = table.sort_values("date").reset_index(drop=True)
    oni = table["oni"]

    frame = pd.DataFrame({"date": table["date"]})
    for k, column in zip(LAGS, LAG_COLUMNS, strict=True):
        frame[column] = oni.shift(k - 1)  # lag 1 is the anchor month itself
    for h, column in zip(LEADS, TARGET_COLUMNS, strict=True):
        frame[column] = oni.shift(-h)  # negative shift looks h months ahead

    return frame.dropna(subset=LAG_COLUMNS).reset_index(drop=True)


def add_era5_lags(frame: pd.DataFrame, era5: pd.DataFrame) -> pd.DataFrame:
    """Add ERA5_LAG_COLUMNS to a build_features frame, matched by date (gaps cannot shift them).

    `era5` needs `date` and the ERA5 anomaly columns. Rows missing any ERA5 lag are dropped.
    """
    era5 = era5.set_index("date")[ERA5_COLUMNS]
    frame = frame.copy()
    for k in ERA5_LAGS:
        values = era5.reindex(frame["date"] - pd.DateOffset(months=k - 1))  # lag 1 is B itself
        for column in ERA5_COLUMNS:
            frame[f"{column}_lag{k}"] = values[column].to_numpy()
    return frame.dropna(subset=ERA5_LAG_COLUMNS).reset_index(drop=True)


def _last_target_date(frame: pd.DataFrame) -> pd.Series:
    """Date of the furthest target for each row (anchor plus the longest lead)."""
    return frame["date"] + pd.DateOffset(months=max(LEADS))


def split_by_date(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split rows into train, validation, and test by the anchor month's year.

    Train and validation rows whose furthest target falls in a later period are
    dropped, so no target crosses into the next period.
    """
    year = frame["date"].dt.year
    target_year = _last_target_date(frame).dt.year

    train = (year <= TRAIN_LAST_YEAR) & (target_year <= TRAIN_LAST_YEAR)
    validation = (
        (year > TRAIN_LAST_YEAR)
        & (year <= VALIDATION_LAST_YEAR)
        & (target_year <= VALIDATION_LAST_YEAR)
    )
    test = year > VALIDATION_LAST_YEAR

    return {
        "train": frame[train].reset_index(drop=True),
        "validation": frame[validation].reset_index(drop=True),
        "test": frame[test].reset_index(drop=True),
    }


def main() -> None:
    table = pd.read_csv(ENSO_MONTHLY_PATH, parse_dates=["date"])
    splits = split_by_date(build_features(table))
    for name, part in splits.items():
        first, last = part["date"].min(), part["date"].max()
        print(f"{name:10s} {len(part):4d} rows, anchors {first:%Y-%m} to {last:%Y-%m}")

    latest = splits["test"].iloc[-1]
    print(f"\nLatest anchor (live forecast input): {latest['date']:%Y-%m}")
    print(latest[LAG_COLUMNS].to_string())


if __name__ == "__main__":
    main()
