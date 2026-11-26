"""Cut the Climate Hazards Center's global yearly CHIRPS files to the Philippines box.

Download first (specs/layer2-impact.md, section 10), into data/raw/philippines/chirps_chc/:
  https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/netcdf/byYear/chirps-v2.0.<year>.monthly.nc
Run from backend/:  python -m app.data.cut_chirps
Each chirps-v2.0.<year>.monthly.nc becomes chirps_v2_monthly_ph_chc_<year>.nc with exactly the same
pixel centres as the ERDDAP files in data/raw/philippines/chirps_grid/. The global file can then be
deleted.
"""

from pathlib import Path

import numpy as np
import xarray as xr

from app.data.load_crops import RAW_DIR

ERDDAP_DIR = RAW_DIR / "chirps_grid"
CHC_DIR = RAW_DIR / "chirps_chc"
MARGIN = 0.001  # degrees; pixel centres are float32, so a tiny margin keeps the edge pixels


def cut_year(global_path: Path, reference: xr.DataArray) -> Path:
    precip = xr.open_dataset(global_path)["precip"]
    if precip["latitude"][0] > precip["latitude"][-1]:
        precip = precip.sortby("latitude")
    cut = precip.sel(
        latitude=slice(float(reference["latitude"].min()) - MARGIN, float(reference["latitude"].max()) + MARGIN),
        longitude=slice(float(reference["longitude"].min()) - MARGIN, float(reference["longitude"].max()) + MARGIN),
    ).load()
    if not (np.allclose(cut["latitude"], reference["latitude"], atol=MARGIN)
            and np.allclose(cut["longitude"], reference["longitude"], atol=MARGIN)):
        raise ValueError(f"{global_path.name}: pixel centres do not match the ERDDAP grid")
    # Copy the ERDDAP coordinates exactly, so the two sources line up in xarray.concat.
    cut = cut.assign_coords(latitude=reference["latitude"].values, longitude=reference["longitude"].values)
    year = global_path.name.split(".")[2]  # chirps-v2.0.<year>.monthly.nc
    out_path = global_path.with_name(f"chirps_v2_monthly_ph_chc_{year}.nc")
    cut.to_dataset(name="precip").to_netcdf(out_path)
    return out_path


def main() -> None:
    reference = xr.open_dataset(min(ERDDAP_DIR.glob("chirps_v2_monthly_ph_*.nc")))["precip"]
    global_files = sorted(CHC_DIR.glob("chirps-v2.0.*.monthly.nc"))
    if not global_files:
        print(f"No global files in {CHC_DIR}")
    for global_path in global_files:
        out_path = cut_year(global_path, reference)
        months = xr.open_dataset(out_path)["time"].dt.strftime("%Y-%m").values
        print(f"{out_path.name}: {len(months)} months, {months[0]} to {months[-1]}")


if __name__ == "__main__":
    main()
