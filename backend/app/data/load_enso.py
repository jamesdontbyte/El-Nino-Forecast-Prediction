"""Load the raw ENSO files, clean them, and save one monthly table.

Run from backend/:  python -m app.data.load_enso
Output: data/processed/enso_monthly.csv with columns date, oni, roni, nino34_anom, soi.
"""

from pathlib import Path

import pandas as pd

# backend/app/data/load_enso.py -> parents[3] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_ENSO_DIR = PROJECT_ROOT / "data" / "raw" / "enso"
NOAA_ONI_PATH = RAW_ENSO_DIR / "oni.ascii.txt"
KAGGLE_PATH = RAW_ENSO_DIR / "dataset_enso_2026.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "enso_monthly.csv"

# Each ONI season is a three-month average. It gets the date of its centre month.
SEASON_TO_CENTRE_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}

# Kaggle column name -> our column name.
KAGGLE_COLUMNS = {
    "RONI": "roni",
    "Nino 3.4 SST Anomaly": "nino34_anom",
    "SOI": "soi",
}


def load_noaa_oni(path: Path = NOAA_ONI_PATH) -> pd.DataFrame:
    """Read NOAA's oni.ascii.txt. Returns columns date and oni."""
    noaa = pd.read_csv(path, sep=r"\s+")  # columns are separated by runs of spaces

    month = noaa["SEAS"].map(SEASON_TO_CENTRE_MONTH)
    unknown = noaa.loc[month.isna(), "SEAS"].unique()
    if len(unknown) > 0:
        raise ValueError(f"Unknown season codes in {path.name}: {list(unknown)}")

    date = pd.to_datetime({"year": noaa["YR"], "month": month, "day": 1})
    return pd.DataFrame({"date": date, "oni": noaa["ANOM"]})


def load_kaggle_indices(path: Path = KAGGLE_PATH) -> pd.DataFrame:
    """Read the Kaggle ENSO file using the loader rules in specs/layer1-forecast.md.

    Returns columns date, roni, nino34_anom, soi. The Kaggle ONI column (only for
    comparison), the phase columns (never a feature), and the Season columns are left out.
    """
    kaggle = pd.read_csv(path)
    kaggle.columns = kaggle.columns.str.strip()  # e.g. "  ONI" -> "ONI"
    kaggle = kaggle.drop(columns=["Unnamed: 0"])

    kaggle = kaggle[["Date", *KAGGLE_COLUMNS]].rename(columns={"Date": "date", **KAGGLE_COLUMNS})
    kaggle["date"] = pd.to_datetime(kaggle["date"], format="%m/%d/%Y")

    # Placeholder months at the end of 2026 have no values at all.
    value_columns = list(KAGGLE_COLUMNS.values())
    placeholder = kaggle[value_columns].isna().all(axis=1)
    return kaggle[~placeholder].reset_index(drop=True)


def build_enso_monthly(noaa: pd.DataFrame, kaggle: pd.DataFrame) -> pd.DataFrame:
    """Join on the month. NOAA is the base, so every NOAA month is kept.

    Kaggle columns are empty (NaN) for months after the Kaggle file ends.
    """
    table = noaa.merge(kaggle, on="date", how="left", validate="one_to_one")
    table = table.sort_values("date").reset_index(drop=True)

    if table["date"].duplicated().any():
        raise ValueError("Duplicate months in the joined table.")
    expected = pd.date_range(table["date"].min(), table["date"].max(), freq="MS")
    missing = expected.difference(table["date"])
    if len(missing) > 0:
        raise ValueError(f"Missing months in the joined table: {list(missing.strftime('%Y-%m'))}")

    return table


def main() -> None:
    table = build_enso_monthly(load_noaa_oni(), load_kaggle_indices())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    print(f"Saved {len(table)} rows to {OUTPUT_PATH}")
    print(f"Dates: {table['date'].min():%Y-%m} to {table['date'].max():%Y-%m}")
    print("Missing values per column:")
    print(table.isna().sum().to_string())


if __name__ == "__main__":
    main()
