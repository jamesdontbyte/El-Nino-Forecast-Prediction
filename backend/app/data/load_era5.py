"""Read the ERA5 files, join the two Pacific halves, and save monthly box averages.

Run from backend/:  python -m app.data.load_era5
Output: data/processed/era5_monthly.csv, one row per month, with
- date: first day of the month
- preliminary: True for ERA5T months (expver 0005), which ECMWF may still revise
- raw box averages, unit in the name (RAW_COLUMNS)
- anomalies against the 1950 to 2008 calendar-month normals (FEATURE_COLUMNS)

The files are found by content, not by name: every .nc file under data/raw/era5/ is
opened and put in the west half (120 to 180) or the east half (-180 to -70) by its
longitudes. Each half comes as two files (tp, and u10/v10/msl/sst).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from app.data.load_enso import OUTPUT_PATH as ENSO_MONTHLY_PATH
from app.data.load_enso import PROJECT_ROOT

RAW_ERA5_DIR = PROJECT_ROOT / "data" / "raw" / "era5"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "era5_monthly.csv"

VARIABLES = {"sst", "u10", "v10", "msl", "tp"}
KNOWN_EXPVER = {"0001": False, "0005": True}  # expver -> preliminary
FIRST_YEAR = 1950
BASE_LAST_YEAR = 2008  # last training year (features.TRAIN_LAST_YEAR)

# Anomaly column -> raw column it is computed from.
FEATURES = {
    "era5_sst_nino34": "sst_nino34_rel_k",
    "era5_u10_west": "u10_west_ms",
    "era5_mslp_diff": "mslp_diff_hpa",
    "era5_tp_central": "tp_central_mm_day",
}
RAW_COLUMNS = list(FEATURES.values())
FEATURE_COLUMNS = list(FEATURES)


def open_era5_file(path: Path) -> xr.Dataset:
    """Open one file, with time as `date` set to the first of each month."""
    ds = xr.open_dataset(path).drop_vars("number", errors="ignore")
    ds = ds.rename({"valid_time": "date"})
    # tp is stamped 06:00 and the other variables 00:00, so round down to the month.
    month_start = ds["date"].values.astype("datetime64[M]").astype("datetime64[ns]")
    return ds.assign_coords(date=month_start)


def half_of(ds: xr.Dataset) -> str:
    """'west' for 120 to 180, 'east' for -180 to -70. Anything else is an error."""
    low, high = float(ds["longitude"].min()), float(ds["longitude"].max())
    if 120 <= low and high <= 180:
        return "west"
    if -180 <= low and high <= -70:
        return "east"
    raise ValueError(f"Longitudes {low} to {high} fit neither ERA5 half.")


def load_halves(raw_dir: Path = RAW_ERA5_DIR) -> dict[str, xr.Dataset]:
    """Open every .nc file under raw_dir and merge the files of each half."""
    groups: dict[str, list[xr.Dataset]] = {"west": [], "east": []}
    for path in sorted(raw_dir.rglob("*.nc")):
        ds = open_era5_file(path)
        groups[half_of(ds)].append(ds)

    halves = {}
    for half, files in groups.items():
        if not files:
            raise ValueError(f"No ERA5 file for the {half} half under {raw_dir}.")
        # join="exact": the files of a half must share the same months and grid.
        merged = xr.merge(files, join="exact", compat="no_conflicts")
        missing = VARIABLES - set(merged.data_vars)
        if missing:
            raise ValueError(f"The {half} half is missing {sorted(missing)}.")
        halves[half] = merged
    return halves


def join_halves(west: xr.Dataset, east: xr.Dataset) -> xr.Dataset:
    """Join on longitude in 0 to 360, keeping the shared 180 column once.

    The shared column must match in every variable and every month (NaN counts as equal).
    """
    east = east.assign_coords(longitude=east["longitude"] % 360)  # -180..-70 -> 180..290

    if set(west.data_vars) != set(east.data_vars):
        raise ValueError("The two halves have different variables.")
    for name in ("date", "latitude", "expver"):
        if not np.array_equal(west[name].values, east[name].values):
            raise ValueError(f"The two halves have different {name} values.")

    shared = np.intersect1d(west["longitude"].values, east["longitude"].values)
    for lon in shared:
        for variable in west.data_vars:
            same = np.array_equal(
                west[variable].sel(longitude=lon).values,
                east[variable].sel(longitude=lon).values,
                equal_nan=True,
            )
            if not same:
                raise ValueError(f"The {lon} column differs between the halves in {variable}.")
    east = east.drop_sel(longitude=shared)

    grid = xr.concat([west, east], dim="longitude", coords="minimal", compat="override")
    steps = np.diff(grid["longitude"].values)
    if not np.allclose(steps, steps[0]):
        raise ValueError("The joined longitudes are not evenly spaced (gap or overlap).")
    return grid


def box_mean(field: xr.DataArray, south: float, north: float, west: float, east: float) -> pd.Series:
    """Area average over a box, weighted by cos(latitude). Land cells (NaN) are left out.

    Longitudes are 0 to 360. Works whichever way latitude is sorted.
    """
    lat, lon = field["latitude"], field["longitude"]
    box = field.sel(
        latitude=lat[(lat >= south) & (lat <= north)],
        longitude=lon[(lon >= west) & (lon <= east)],
    )
    if box.sizes["latitude"] == 0 or box.sizes["longitude"] == 0:
        raise ValueError(f"Empty box {south} to {north}, {west} to {east}.")
    weights = np.cos(np.deg2rad(box["latitude"]))
    return box.weighted(weights).mean(["latitude", "longitude"]).to_series()


def box_averages(grid: xr.Dataset) -> pd.DataFrame:
    """One row per month: preliminary flag and the raw box averages (boxes in spec section 13)."""
    expver = pd.Series(grid["expver"].values, index=grid["date"].values)
    unknown = set(expver) - set(KNOWN_EXPVER)
    if unknown:
        raise ValueError(f"Unknown expver values: {sorted(unknown)}")

    sst, msl = grid["sst"], grid["msl"]
    table = pd.DataFrame({
        "preliminary": expver.map(KNOWN_EXPVER),
        # Relative index (like RONI): Nino 3.4 minus the 20S-20N average, so the warming trend cancels.
        "sst_nino34_rel_k": box_mean(sst, -5, 5, 190, 240) - box_mean(sst, -20, 20, 120, 290),
        "u10_west_ms": box_mean(grid["u10"], -5, 5, 120, 180),
        # Tahiti minus Darwin, Pa -> hPa.
        "mslp_diff_hpa": (box_mean(msl, -20, -15, 208, 213) - box_mean(msl, -15, -10, 128, 133)) / 100,
        # ERA5 monthly tp is the mean daily total in metres, so x1000 gives mm per day.
        "tp_central_mm_day": box_mean(grid["tp"], -5, 5, 170, 220) * 1000,
    })
    return table.rename_axis("date").reset_index()


def add_anomalies(
    table: pd.DataFrame, base_first_year: int = FIRST_YEAR, base_last_year: int = BASE_LAST_YEAR
) -> pd.DataFrame:
    """Add FEATURE_COLUMNS: each raw value minus its calendar month's base-period average.

    Only base years set the normals, so later data never leaks in. Use base_first_year=1979
    for the 1979 check.
    """
    month = table["date"].dt.month
    in_base = table["date"].dt.year.between(base_first_year, base_last_year)
    normals = table[in_base].groupby(month[in_base])[RAW_COLUMNS].mean()
    if len(normals) != 12:
        raise ValueError(f"The base period {base_first_year} to {base_last_year} lacks some months.")

    table = table.copy()
    for feature, raw in FEATURES.items():
        table[feature] = table[raw] - normals[raw].reindex(month).to_numpy()
    return table


def build_era5_monthly(grid: xr.Dataset) -> pd.DataFrame:
    """Box averages plus anomalies, from FIRST_YEAR on. Fails on gaps or empty values."""
    grid = grid.sel(date=slice(f"{FIRST_YEAR}-01-01", None))
    table = add_anomalies(box_averages(grid))

    expected = pd.date_range(table["date"].min(), table["date"].max(), freq="MS")
    if len(expected) != len(table) or not expected.equals(pd.DatetimeIndex(table["date"])):
        raise ValueError("ERA5 months have gaps or duplicates.")
    if table.isna().any().any():
        raise ValueError(f"Empty values:\n{table.isna().sum().to_string()}")
    return table


def main() -> None:
    halves = load_halves()
    table = build_era5_monthly(join_halves(halves["west"], halves["east"]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    print(f"Saved {len(table)} rows to {OUTPUT_PATH}")
    print(f"Dates: {table['date'].min():%Y-%m} to {table['date'].max():%Y-%m}")
    print(f"Preliminary months: {list(table.loc[table['preliminary'], 'date'].dt.strftime('%Y-%m'))}")
    base = table[table["date"].dt.year <= BASE_LAST_YEAR]
    print(f"Mean anomaly in {FIRST_YEAR} to {BASE_LAST_YEAR} (should be ~0):")
    print(base[FEATURE_COLUMNS].mean().round(6).to_string())
    print("Raw averages over all months:")
    print(table[RAW_COLUMNS].mean().round(3).to_string())
    if ENSO_MONTHLY_PATH.exists():
        newest_oni = pd.read_csv(ENSO_MONTHLY_PATH, parse_dates=["date"])["date"].max()
        print(f"Newest ERA5 month: {table['date'].max():%Y-%m}; newest ONI month: {newest_oni:%Y-%m}")


if __name__ == "__main__":
    main()
