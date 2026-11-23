"""Load the PSA palay and corn tables, clean them, and save one quarterly table.

Run from backend/:  python -m app.data.load_crops
Output: data/processed/crops_quarterly.csv with columns crop_type, province, year,
quarter, area_ha, production_t, yield_t_per_ha. Cleaning rules: specs/layer2-impact.md.
"""

from pathlib import Path

import pandas as pd

# backend/app/data/load_crops.py -> parents[3] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "philippines"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "crops_quarterly.csv"

# (area file, production file) per crop. Each file holds the crop's three crop types.
CROP_FILES = [
    (RAW_DIR / "palay_areas.csv", RAW_DIR / "palay_production.csv"),
    (RAW_DIR / "corn_area.csv", RAW_DIR / "corn_production.csv"),
]

# Raw PSA name (dots stripped, footnote kept) -> cleaned province name.
# Names not listed pass through unchanged.
PROVINCE_FIXES = {
    # Negros Island Region rows (2024 on) continue the old rows (1987 to 2023).
    "Negros Occidental a/": "Negros Occidental",
    "Negros Oriental b/": "Negros Oriental",
    "Siquijor b/": "Siquijor",
    # Sulu moved to Region IX: the c/ row has data only from 2026, the BARMM row up to 2025.
    "Sulu c/": "Sulu",
    # City rows are added into the province that surrounds them.
    "Bacolod City": "Negros Occidental",
    "Butuan City": "Agusan del Norte",
    "City of Davao": "Davao del Sur",
    "Puerto Princesa City": "Palawan",
    "Zamboanga City": "Zamboanga del Sur",
    # Split provinces are merged back, because CHIRPS rainfall uses the old boundaries.
    "Maguindanao del Norte": "Maguindanao",
    "Maguindanao del Sur": "Maguindanao",
    "Davao Occidental": "Davao del Sur",
    # Names that differ from the map shapes.
    "Cotabato (North Cotabato)": "Cotabato",
    "Davao de Oro (Compostela Valley)": "Davao de Oro",
    "Tawi-tawi": "Tawi-Tawi",
}

KEYS = ["crop_type", "province", "year", "quarter"]


def read_psa_table(path: Path, value_name: str) -> pd.DataFrame:
    """Read one PSA file into a long table of province rows and quarter values.

    Returns columns crop_type, location, year, quarter and value_name. location is the
    raw name with the leading dots stripped and any footnote kept.
    """
    table = pd.read_csv(path, sep=";", skiprows=2, na_values="..")
    table = table.rename(columns={table.columns[0]: "crop_type", "Geolocation": "location"})

    # Four leading dots mark a province or city. Region and national rows are not used,
    # so the region-only BARMM area from 2023 on is left out (decided: leave it out for now).
    table = table[table["location"].str.startswith("....")].copy()
    table["location"] = table["location"].str.lstrip(".").str.strip()

    quarter_columns = [c for c in table.columns if "Quarter" in c]
    long = table.melt(id_vars=["crop_type", "location"], value_vars=quarter_columns,
                      var_name="period", value_name=value_name)
    period = long.pop("period").str.extract(r"(\d{4}) Quarter (\d)").astype(int)
    long["year"], long["quarter"] = period[0], period[1]
    return long


def clean_locations(long: pd.DataFrame) -> pd.DataFrame:
    """Map every raw location name to its cleaned province."""
    # A footnote we have not seen means PSA changed the table. Stop rather than guess.
    footnoted = long["location"].str.contains(r"\s[a-z]/$")
    unknown = sorted(set(long.loc[footnoted, "location"]) - set(PROVINCE_FIXES))
    if unknown:
        raise ValueError(f"Unknown footnoted rows: {unknown}")

    long = long.copy()
    long["province"] = long.pop("location").replace(PROVINCE_FIXES)
    return long


def load_crop(area_path: Path, production_path: Path) -> pd.DataFrame:
    """Load one crop (palay or corn): join area and production, clean, and compute yield."""
    area = read_psa_table(area_path, "area_ha")
    production = read_psa_table(production_path, "production_t")
    # Join on the raw location, before merging provinces. Joining after the merge would
    # pair every area row with every production row of a merged province and inflate sums.
    raw_keys = ["crop_type", "location", "year", "quarter"]
    both = area.merge(production, on=raw_keys, how="outer", validate="one_to_one")
    both = clean_locations(both)

    # Summing joins the Negros rows, merges split provinces, and adds cities. Area and
    # production are summed before yield is computed. min_count=1 keeps all-missing as NaN.
    both = both.groupby(KEYS, as_index=False)[["area_ha", "production_t"]].sum(min_count=1)

    # Zero or missing area has no yield (not a yield of zero).
    has_area = both["area_ha"] > 0
    both["yield_t_per_ha"] = (both["production_t"] / both["area_ha"]).where(has_area)
    return both


def load_crops(crop_files: list[tuple[Path, Path]] = CROP_FILES) -> pd.DataFrame:
    """Load every crop into one table, sorted by crop type, province, year and quarter."""
    table = pd.concat([load_crop(a, p) for a, p in crop_files], ignore_index=True)
    return table.sort_values(KEYS).reset_index(drop=True)


def main() -> None:
    table = load_crops()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(table)} rows to {OUTPUT_PATH}")
    print(f"Crop types: {sorted(table['crop_type'].unique())}")
    print(f"Provinces: {table['province'].nunique()}")
    print(f"Years: {table['year'].min()} to {table['year'].max()}")
    print(f"Rows with a yield: {table['yield_t_per_ha'].notna().sum()}")


if __name__ == "__main__":
    main()
