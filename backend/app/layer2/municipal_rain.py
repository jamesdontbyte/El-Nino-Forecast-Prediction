"""Quarterly rain % of normal for each municipality from the CHIRPS grid (specs/layer2-impact.md, section 11).

Run from backend/:  python -m app.layer2.municipal_rain   (about a minute)
Output: data/processed/municipal_rain_quarterly.csv with columns adm3_psgc, name, map_psgc,
year, quarter, rain_mm, normal_mm, rain_pct_of_normal, n_pixels, pixel_rule.

Which grid squares a municipality uses (pixel_rule):
- "inside": every land square whose centre is inside the shape.
- "nearest": no centre is inside (small municipalities), so the land square nearest to a point
  inside the shape, if it is within MAX_DISTANCE_DEG. This includes the square holding that point.
- "none": nothing within reach (for example a tiny island far from other land). No rain value.
"""

import json

import numpy as np
import pandas as pd
from matplotlib.path import Path as ShapePath

from app.data.load_crops import RAW_DIR
from app.data.load_rainfall import OUTPUT_PATH as PROVINCE_QUARTERS_PATH
from app.layer2.grid_rain import (
    NORMAL_YEARS,
    load_grid,
    normal_by_quarter,
    pixels_inside,
    quarterly_rain,
)

MUNICIPAL_DIR = RAW_DIR / "Municipality"
OUTPUT_PATH = PROVINCE_QUARTERS_PATH.parent / "municipal_rain_quarterly.csv"
MAX_DISTANCE_DEG = 0.05  # one grid square, about 5.5 km


def load_municipalities(folder=MUNICIPAL_DIR) -> list[dict]:
    files = sorted(folder.glob("municities-provdist-*.json"))
    if not files:
        raise FileNotFoundError(f"No municipal shape files in {folder}")
    rows = []
    for path in files:
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            props = feature["properties"]
            rows.append({"adm3_psgc": str(props["adm3_psgc"]).zfill(10), "name": props["adm3_en"],
                         # The file's province code, not digits of adm3_psgc: 34 cities differ.
                         "map_psgc": str(props["adm2_psgc"]).zfill(10), "geometry": feature["geometry"]})
    return rows


def ring_area(ring) -> float:
    x, y = np.asarray(ring, dtype=float).T
    return abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2


def point_inside(geometry: dict) -> tuple[float, float]:
    """A point inside the largest part of the shape (a plain centroid can fall at sea)."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    outer = np.asarray(max((polygon[0] for polygon in polygons), key=ring_area), dtype=float)
    path = ShapePath(outer)
    mean_point = outer.mean(axis=0)
    if path.contains_point(mean_point):
        return tuple(mean_point)
    # Otherwise try the centres of a 25 x 25 split of the shape's box (centres, so no point sits on
    # an edge that lines up with the box); take the inside one nearest the mean.
    steps = (np.arange(25) + 0.5) / 25
    xs = outer[:, 0].min() + steps * np.ptp(outer[:, 0])
    ys = outer[:, 1].min() + steps * np.ptp(outer[:, 1])
    candidates = np.array([(x, y) for x in xs for y in ys])
    inside = candidates[path.contains_points(candidates)]
    if len(inside) == 0:
        return tuple(mean_point)  # a sliver thinner than the sample spacing; the mean is close enough
    return tuple(inside[np.argmin(((inside - mean_point) ** 2).sum(axis=1))])


def choose_pixels(geometry: dict, lats: np.ndarray, lons: np.ndarray, land: np.ndarray) -> tuple[np.ndarray, str]:
    mask = pixels_inside(geometry, lats, lons) & land
    if mask.any():
        return mask, "inside"
    lon, lat = point_inside(geometry)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    distance = np.hypot(lon_grid - lon, lat_grid - lat)
    distance[~land] = np.inf
    nearest = np.unravel_index(np.argmin(distance), distance.shape)
    mask = np.zeros(land.shape, dtype=bool)
    if distance[nearest] > MAX_DISTANCE_DEG:
        return mask, "none"
    mask[nearest] = True
    return mask, "nearest"


def municipal_rain() -> pd.DataFrame:
    grid = load_grid()
    lats, lons = grid["latitude"].values, grid["longitude"].values
    land = ~np.isnan(grid.values).all(axis=0)
    tables = []
    for municipality in load_municipalities():
        mask, rule = choose_pixels(municipality["geometry"], lats, lons, land)
        info = {key: municipality[key] for key in ("adm3_psgc", "name", "map_psgc")}
        if rule == "none":
            tables.append(pd.DataFrame([{**info, "n_pixels": 0, "pixel_rule": rule}]))
            continue
        quarters = quarterly_rain(grid, mask)
        # Ratio of sums (section 6): the mean quarter total over the normal years, not a mean of percents.
        quarters["normal_mm"] = quarters["quarter"].map(normal_by_quarter(quarters, NORMAL_YEARS))
        quarters["rain_pct_of_normal"] = quarters["rain_mm"] / quarters["normal_mm"] * 100
        tables.append(quarters.assign(**info, n_pixels=int(mask.sum()), pixel_rule=rule))
    columns = ["adm3_psgc", "name", "map_psgc", "year", "quarter", "rain_mm", "normal_mm",
               "rain_pct_of_normal", "n_pixels", "pixel_rule"]
    return pd.concat(tables, ignore_index=True)[columns]


def main() -> None:
    table = municipal_rain()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False)
    per_municipality = table.drop_duplicates("adm3_psgc")
    print(f"Saved {len(table)} rows for {len(per_municipality)} municipalities to {OUTPUT_PATH}")
    print(per_municipality["pixel_rule"].value_counts().to_string())


if __name__ == "__main__":
    main()
