"""Municipal map view for one forecast quarter and one past-data view (specs/layer2-impact.md, section 11).

The prediction view is per province only (decided 2026-11-26), so only the views in
MUNICIPAL_VIEWS exist here. The year each view shows comes from the province map
(load_map_views), so both maps always show the same year.
Reads data/processed/municipal_rain_quarterly.csv (python -m app.layer2.municipal_rain).
"""

from functools import cache
from pathlib import Path

import pandas as pd

from app.layer2.features import load_lookup
from app.layer2.map_output import dryness_colour, load_map_views
from app.layer2.municipal_rain import MUNICIPAL_DIR, load_municipalities
from app.layer2.municipal_rain import OUTPUT_PATH as MUNICIPAL_RAIN_PATH
from app.layer2.shapes import round_coordinates

MUNICIPAL_VIEWS = ["normal", "el_nino_2015_16", "el_nino_2023_24"]


class BadMapRequest(ValueError):
    """An unknown quarter or view. Its own class, so other ValueErrors are not reported as bad input."""


@cache  # built once per folder and kept in memory, like load_shapes; a failed build is not cached
def load_municipal_shapes(folder: Path = MUNICIPAL_DIR) -> dict:
    """The 1,642 municipal shapes as one FeatureCollection, coordinates rounded to 3 decimals."""
    features = [{
        "type": "Feature",
        "properties": {key: municipality[key] for key in ("adm3_psgc", "name", "map_psgc")},
        "geometry": {"type": municipality["geometry"]["type"],
                     "coordinates": round_coordinates(municipality["geometry"]["coordinates"])},
    } for municipality in load_municipalities(folder)]
    return {"type": "FeatureCollection", "features": features}


def load_municipal_rain(path=MUNICIPAL_RAIN_PATH) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"adm3_psgc": str, "map_psgc": str})


def municipal_rows(rain: pd.DataFrame, lookup: pd.DataFrame, year: int | None, quarter: int) -> list[dict]:
    """One row per municipality. No rain for that quarter (Kalayaan, or no year) gives null and grey."""
    municipalities = rain[["adm3_psgc", "map_psgc"]].drop_duplicates("adm3_psgc")
    this_quarter = rain[(rain["year"] == year) & (rain["quarter"] == quarter)]
    rows = municipalities.merge(this_quarter[["adm3_psgc", "rain_pct_of_normal"]], on="adm3_psgc", how="left")
    provinces = lookup.assign(map_psgc=lookup["map_psgc"].str.zfill(10)).set_index("map_psgc")["crop_name"]
    result = []
    for row in rows.itertuples():
        rain_pct = None if pd.isna(row.rain_pct_of_normal) else round(float(row.rain_pct_of_normal), 1)
        province = provinces.get(row.map_psgc)
        result.append({
            "adm3_psgc": row.adm3_psgc,
            "map_psgc": row.map_psgc,
            "province": None if pd.isna(province) else province,  # null for the no-crop areas
            "rain_pct": rain_pct,
            "colour": dryness_colour(rain_pct),  # same PAGASA bands on the rounded value
        })
    return result


def load_municipal_map(quarter_label: str, view: str) -> dict:
    """Raises BadMapRequest for an unknown quarter or view (the route turns it into a 422)."""
    if view not in MUNICIPAL_VIEWS:
        raise BadMapRequest(f"Unknown municipal view: {view!r}. Choose one of {MUNICIPAL_VIEWS}. "
                         "The prediction view is per province: see /api/map.")
    quarters = {entry["quarter"]: entry for entry in load_map_views()}
    if quarter_label not in quarters:
        raise BadMapRequest(f"Unknown quarter: {quarter_label!r}. Choose one of {list(quarters)}.")
    year = quarters[quarter_label]["views"][view]["year"]
    quarter = int(quarter_label.split("Q")[1])  # labels look like "2026 Q4"
    return {"quarter": quarter_label, "view": view, "year": year,
            # The path is read at call time, so a test can point it elsewhere.
            "municipalities": municipal_rows(load_municipal_rain(MUNICIPAL_RAIN_PATH), load_lookup(), year, quarter)}
