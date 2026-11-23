"""Build the Layer 2 tables: quarterly ONI, the normal yield, yield change, and the split.

Two tables, one per model step (decisions in specs/layer2-impact.md):
- Rainfall table: one row per province (CHIRPS pcode), year and quarter. Target is rainfall
  percent of normal. Inputs are this quarter's and last quarter's ONI.
- Yield table: one row per province, crop type, year and quarter. Target is yield change
  against the normal, clipped to -100 .. +100 percent. Inputs are this quarter's and last
  quarter's rainfall percent of normal and ONI.

"Last quarter" is found by quarter number (year x 4 + quarter - 1), not by row order, so
Q1 uses the previous year's Q4 and a missing quarter gives an empty value.

Run from backend/:  python -m app.layer2.features   (prints the table and split sizes)
"""

from pathlib import Path

import numpy as np
import pandas as pd

from app.data.load_crops import load_crops
from app.data.load_rainfall import load_rainfall
from app.layer1_forecast.features import TRAIN_LAST_YEAR, VALIDATION_LAST_YEAR
from app.layer1_forecast.models import load_enso_monthly

LOOKUP_PATH = Path(__file__).resolve().parents[1] / "data" / "province_lookup.csv"

NORMAL_YEARS = 10  # decided: straight line through the 10 years before the scored year
CLIP_PERCENT = 100  # decided: yield change is clipped to -100 .. +100 percent

RAIN_TARGET = "rain_pct_of_normal"
YIELD_TARGET = "yield_change_pct"
RAIN_NUMERIC = ["oni", "oni_prev"]
RAIN_CATEGORICAL = ["quarter", "pcode"]
YIELD_NUMERIC = ["rain_pct", "rain_pct_prev", "oni", "oni_prev"]
YIELD_NUMERIC_THIS_QUARTER = ["rain_pct", "oni"]  # for the lag check
YIELD_CATEGORICAL = ["crop_type", "quarter", "pcode"]


def quarter_number(year: pd.Series, quarter: pd.Series) -> pd.Series:
    """Count quarters from year 0, so the previous quarter is always this number minus 1."""
    return year * 4 + quarter - 1


def quarterly_oni(enso: pd.DataFrame) -> pd.DataFrame:
    """Mean ONI per calendar quarter. Quarters without all 3 months are left out.

    `enso` needs columns `date` (first day of each month) and `oni`.
    """
    monthly = enso[["date", "oni"]].dropna()
    monthly = monthly.assign(year=monthly["date"].dt.year, quarter=monthly["date"].dt.quarter)
    quarters = monthly.groupby(["year", "quarter"], as_index=False).agg(
        oni=("oni", "mean"), months=("oni", "size"))
    quarters = quarters[quarters["months"] == 3].drop(columns="months")
    return quarters.reset_index(drop=True)


def add_previous_quarter(table: pd.DataFrame, column: str, keys: list[str]) -> pd.DataFrame:
    """Add `<column>_prev`: the value for the same keys one quarter earlier (empty if missing)."""
    t = quarter_number(table["year"], table["quarter"])
    previous = table[keys + [column]].assign(t=t + 1)  # last quarter's row, moved forward one step
    previous = previous.rename(columns={column: f"{column}_prev"})
    return table.assign(t=t).merge(previous, on=keys + ["t"], how="left", validate="one_to_one").drop(columns="t")


def oni_with_previous(enso: pd.DataFrame) -> pd.DataFrame:
    return add_previous_quarter(quarterly_oni(enso), "oni", keys=[])


def normal_yield(crops: pd.DataFrame) -> pd.Series:
    """The normal yield for each row: a straight line through the 10 years before its year.

    Fitted separately for each crop type, province and quarter. All 10 earlier years must have
    a yield, otherwise the normal is empty ("not enough data"). Only past years are used, so
    the scored year never helps build its own normal.
    """
    cell = ["crop_type", "province", "quarter"]
    x = np.arange(NORMAL_YEARS)

    def line_forward(window: np.ndarray) -> float:
        slope, intercept = np.polyfit(x, window, 1)
        return slope * NORMAL_YEARS + intercept  # one year after the window

    normals = []
    for _, group in crops.groupby(cell):
        by_year = group.set_index("year")["yield_t_per_ha"]
        all_years = by_year.reindex(range(by_year.index.min(), by_year.index.max() + 1))  # gaps become empty
        # rolling() needs all 10 values present; shift(1) so year Y uses Y-10 .. Y-1.
        line = all_years.rolling(NORMAL_YEARS).apply(line_forward, raw=True).shift(1)
        normals.append(pd.Series(line.reindex(by_year.index).to_numpy(), index=group.index))
    return pd.concat(normals).reindex(crops.index)


def yield_change(actual: pd.Series, normal: pd.Series) -> pd.Series:
    """Percent change against the normal, only where the normal is above 0, clipped to +-100."""
    change = (actual - normal) / normal * 100
    return change.where(normal > 0).clip(-CLIP_PERCENT, CLIP_PERCENT)


def build_rain_table(rain: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    """Rainfall rows with this and last quarter's ONI. Rows with any missing value are dropped."""
    table = rain[["pcode", "year", "quarter", RAIN_TARGET]].merge(
        oni, on=["year", "quarter"], how="left", validate="many_to_one")
    return table.dropna(subset=RAIN_NUMERIC + [RAIN_TARGET]).reset_index(drop=True)


def crop_pcodes(lookup: pd.DataFrame) -> pd.DataFrame:
    """One rainfall code per crop province. Merged shapes share a crop name, so remove duplicates."""
    return lookup[["crop_name", "rain_pcode"]].dropna().drop_duplicates()


def build_yield_table(crops: pd.DataFrame, rain: pd.DataFrame, oni: pd.DataFrame,
                      lookup: pd.DataFrame) -> pd.DataFrame:
    """Yield change rows with rainfall and ONI for this and last quarter.

    Only rows where the target and every input exist are kept, so every model is scored
    on the same rows.
    """
    crops = crops.assign(normal_t_per_ha=normal_yield(crops))
    crops[YIELD_TARGET] = yield_change(crops["yield_t_per_ha"], crops["normal_t_per_ha"])

    table = crops.merge(crop_pcodes(lookup), left_on="province", right_on="crop_name",
                        how="left", validate="many_to_one").drop(columns="crop_name")
    if len(table) != len(crops):
        raise ValueError("The province lookup join duplicated rows.")
    table = table.rename(columns={"rain_pcode": "pcode"})

    rain_values = add_previous_quarter(
        rain[["pcode", "year", "quarter", RAIN_TARGET]].rename(columns={RAIN_TARGET: "rain_pct"}),
        "rain_pct", keys=["pcode"])
    table = table.merge(rain_values, on=["pcode", "year", "quarter"], how="left", validate="many_to_one")
    table = table.merge(oni, on=["year", "quarter"], how="left", validate="many_to_one")
    return table.dropna(subset=YIELD_NUMERIC + [YIELD_TARGET]).reset_index(drop=True)


def split_by_year(table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Train up to 2008, validation 2009 to 2016, test 2017 on. Same boundaries as Layer 1."""
    year = table["year"]
    return {
        "train": table[year <= TRAIN_LAST_YEAR].reset_index(drop=True),
        "validation": table[(year > TRAIN_LAST_YEAR) & (year <= VALIDATION_LAST_YEAR)].reset_index(drop=True),
        "test": table[year > VALIDATION_LAST_YEAR].reset_index(drop=True),
    }


def load_lookup() -> pd.DataFrame:
    # Blank crop names (NCR, City of Isabela, Special Geographic Area) become missing values.
    return pd.read_csv(LOOKUP_PATH, dtype=str)


def load_tables() -> dict[str, pd.DataFrame]:
    """Both model tables from the processed data."""
    rain, oni = load_rainfall(), oni_with_previous(load_enso_monthly())
    return {
        "rain": build_rain_table(rain, oni),
        "yield": build_yield_table(load_crops(), rain, oni, load_lookup()),
    }


def main() -> None:
    for name, table in load_tables().items():
        print(f"{name} table: {len(table)} rows, {table['year'].min()} to {table['year'].max()}")
        for part, rows in split_by_year(table).items():
            print(f"  {part:10s} {len(rows):6d} rows, {rows['year'].min()} to {rows['year'].max()}")


if __name__ == "__main__":
    main()
