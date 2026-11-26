"""Rainfall from the CHIRPS 0.05 degree grid, averaged over a shape (specs/layer2-impact.md, section 11).

Run from backend/:  python -m app.layer2.grid_rain
This runs the province check: rebuild the 81 CHIRPS province quarters from the grid and compare
them with the province CSV (rain, normal and pixel count). Output:
data/processed/grid_province_check.csv. Municipal numbers are not built until this check passes.
"""

import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.path import Path as ShapePath

from app.data.load_crops import RAW_DIR
from app.data.load_rainfall import OUTPUT_PATH as PROVINCE_QUARTERS_PATH
from app.data.load_rainfall import RAINFALL_PATH, load_rainfall
from app.layer2.shapes import SHAPES_DIR, load_shapes

GRID_DIR = RAW_DIR / "chirps_grid"
LOOKUP_PATH = RAW_DIR.parents[2] / "backend" / "app" / "data" / "province_lookup.csv"
CHECK_PATH = PROVINCE_QUARTERS_PATH.parent / "grid_province_check.csv"
NORMAL_YEARS = (1989, 2018)  # the HDX HAPI climate guide gives this period for the CSV's rfh_avg
OTHER_PERIODS = [(1981, 2010), (1991, 2020), (1981, 2024)]  # compared, to see which matches best


def load_grid(folder=GRID_DIR) -> xr.DataArray:
    """Monthly rain (mm) as (time, latitude, longitude). Sea pixels are NaN."""
    files = sorted(folder.glob("chirps_v2_monthly_ph_*.nc"))
    if not files:
        raise FileNotFoundError(f"No CHIRPS grid files in {folder}")
    # open_mfdataset would need dask, which is not installed; the box is small enough to load.
    return xr.concat([xr.open_dataset(path)["precip"].load() for path in files], dim="time")


def pixels_inside(geometry: dict, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """True for each grid pixel whose centre is inside the Polygon or MultiPolygon (holes excluded)."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    centres = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
    inside = np.zeros(len(centres), dtype=bool)
    for outer, *holes in polygons:
        in_polygon = ShapePath(outer).contains_points(centres)
        for hole in holes:
            in_polygon &= ~ShapePath(hole).contains_points(centres)
        inside |= in_polygon
    return inside.reshape(lat_grid.shape)


def quarterly_rain(grid: xr.DataArray, mask: np.ndarray) -> pd.DataFrame:
    """Mean rain over the masked land pixels per month, summed into complete calendar quarters."""
    monthly = np.nanmean(grid.values[:, mask], axis=1)
    months = pd.DataFrame({"time": pd.to_datetime(grid["time"].values), "rain_mm": monthly})
    months["year"], months["quarter"] = months["time"].dt.year, months["time"].dt.quarter
    quarters = months.groupby(["year", "quarter"], as_index=False).agg(
        rain_mm=("rain_mm", "sum"), n_months=("rain_mm", "size"))
    return quarters[quarters["n_months"] == 3].drop(columns="n_months").reset_index(drop=True)


def normal_by_quarter(quarters: pd.DataFrame, years: tuple[int, int]) -> pd.Series:
    """Mean quarter total over the given years (inclusive), one value per calendar quarter."""
    chosen = quarters[quarters["year"].between(*years)]
    return chosen.groupby("quarter")["rain_mm"].mean()


def province_check() -> pd.DataFrame:
    grid = load_grid()
    lats, lons = grid["latitude"].values, grid["longitude"].values
    land = ~np.isnan(grid.values).all(axis=0)
    shapes = {feature["properties"]["map_psgc"]: feature["geometry"]
              for feature in load_shapes(SHAPES_DIR)["features"]}
    lookup = pd.read_csv(LOOKUP_PATH, dtype={"map_psgc": str}).dropna(subset=["rain_pcode", "map_psgc"])
    csv_quarters = load_rainfall()
    csv_pixels = pd.read_csv(RAINFALL_PATH, usecols=["adm_level", "PCODE", "n_pixels"]).query(
        "adm_level == 2").groupby("PCODE")["n_pixels"].first()

    rows = []
    for pcode, group in lookup.groupby("rain_pcode"):
        # One CHIRPS unit can be several shapes (old boundaries: Maguindanao, Davao del Sur, NCR).
        mask = np.zeros(land.shape, dtype=bool)
        for code in group["map_psgc"].str.zfill(10).unique():
            mask |= pixels_inside(shapes[code], lats, lons)
        mask &= land
        grid_quarters = quarterly_rain(grid, mask)
        csv = csv_quarters[csv_quarters["pcode"] == pcode]
        both = grid_quarters.merge(csv, on=["year", "quarter"], suffixes=("_grid", "_csv"))
        rain_diff_pct = (both["rain_mm_grid"] / both["rain_mm_csv"] - 1) * 100
        row = {"pcode": pcode, "pixels_grid": int(mask.sum()), "pixels_csv": int(csv_pixels[pcode]),
               "quarters_compared": len(both),
               "rain_diff_pct_median": rain_diff_pct.median(),
               "rain_diff_pct_abs_p90": rain_diff_pct.abs().quantile(0.9)}
        csv_normal = csv.groupby("quarter")["normal_mm"].first()  # rfh_avg is the same every year
        for years in [NORMAL_YEARS, *OTHER_PERIODS]:
            normal_diff_pct = (normal_by_quarter(grid_quarters, years) / csv_normal - 1) * 100
            row[f"normal_diff_pct_{years[0]}_{years[1]}"] = normal_diff_pct.abs().mean()
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    check = province_check()
    CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
    check.to_csv(CHECK_PATH, index=False)
    print(f"Saved {len(check)} provinces to {CHECK_PATH}")
    print(check.drop(columns="pcode").describe().round(2).to_string())


if __name__ == "__main__":
    main()
