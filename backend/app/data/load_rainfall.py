"""Load CHIRPS ten-day rainfall and turn it into calendar quarters per province.

Run from backend/:  python -m app.data.load_rainfall
Output: data/processed/rainfall_quarterly.csv with columns pcode, year, quarter, rain_mm,
normal_mm, rain_pct_of_normal, n_dekads, n_prelim.
"""

from pathlib import Path

import pandas as pd

# backend/app/data/load_rainfall.py -> parents[3] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAINFALL_PATH = PROJECT_ROOT / "data" / "raw" / "philippines" / "phl-rainfall-subnat-full.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "rainfall_quarterly.csv"

PROVINCE_LEVEL = 2
DEKADS_PER_QUARTER = 9  # three ten-day periods per month


def load_rainfall(path: Path = RAINFALL_PATH) -> pd.DataFrame:
    """Sum ten-day rainfall into quarters for each province.

    Rule A (decided): rain_pct_of_normal = quarter total / quarter normal * 100. Quarters
    with fewer than nine ten-day rows are incomplete and dropped.
    """
    rain = pd.read_csv(path, usecols=["date", "adm_level", "PCODE", "rfh", "rfh_avg", "version"],
                       parse_dates=["date"])
    rain = rain[rain["adm_level"] == PROVINCE_LEVEL]
    rain = rain.assign(pcode=rain["PCODE"], year=rain["date"].dt.year,
                       quarter=rain["date"].dt.quarter, prelim=rain["version"] == "prelim")

    quarterly = rain.groupby(["pcode", "year", "quarter"], as_index=False).agg(
        rain_mm=("rfh", "sum"), normal_mm=("rfh_avg", "sum"),
        n_dekads=("rfh", "size"), n_prelim=("prelim", "sum"),
    )
    quarterly = quarterly[quarterly["n_dekads"] == DEKADS_PER_QUARTER].copy()
    quarterly["rain_pct_of_normal"] = quarterly["rain_mm"] / quarterly["normal_mm"] * 100
    columns = ["pcode", "year", "quarter", "rain_mm", "normal_mm", "rain_pct_of_normal",
               "n_dekads", "n_prelim"]
    return quarterly[columns].reset_index(drop=True)


def main() -> None:
    table = load_rainfall()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False)

    periods = table.sort_values(["year", "quarter"])
    first, last = periods.iloc[0], periods.iloc[-1]
    print(f"Saved {len(table)} rows to {OUTPUT_PATH}")
    print(f"Provinces: {table['pcode'].nunique()}")
    print(f"Quarters: {first['year']} Q{first['quarter']} to {last['year']} Q{last['quarter']}")
    print(f"Quarters with preliminary rows: {(table['n_prelim'] > 0).sum()}")


if __name__ == "__main__":
    main()
