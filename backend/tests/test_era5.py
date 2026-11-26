import numpy as np
import pandas as pd
import pytest
import xarray as xr

from app.data.load_era5 import (
    FEATURE_COLUMNS,
    RAW_COLUMNS,
    add_anomalies,
    box_mean,
    build_era5_monthly,
    join_halves,
    load_halves,
)

DATES = pd.date_range("2000-01-01", periods=3, freq="MS")
LATS = [20.0, 0.0, -20.0]  # north to south, like the real files


def make_half(lons, variables=("sst", "u10", "v10", "msl", "tp"), hour=0, expver=("0001", "0001", "0005")):
    """Small made-up half. Each value is 1000*month + longitude, so columns are easy to compare."""
    lon = np.array(lons, dtype=float)
    values = (np.arange(len(DATES))[:, None, None] * 1000 + (lon % 360)[None, None, :]) * np.ones((1, len(LATS), 1))
    return xr.Dataset(
        {name: (("valid_time", "latitude", "longitude"), values.copy()) for name in variables},
        coords={
            "valid_time": DATES + pd.Timedelta(hours=hour),
            "latitude": LATS,
            "longitude": lon,
            "expver": ("valid_time", list(expver)),
        },
    )


def test_files_found_by_longitude_and_times_rounded_to_month(tmp_path):
    # Names and folders say nothing about the half; tp is stamped 06:00 like the real files.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    make_half([176, 178, 180], variables=["tp"], hour=6).to_netcdf(tmp_path / "a" / "x1.nc")
    make_half([176, 178, 180], variables=["sst", "u10", "v10", "msl"]).to_netcdf(tmp_path / "b" / "x2.nc")
    make_half([-180, -178], variables=["tp"], hour=6).to_netcdf(tmp_path / "b" / "x3.nc")
    make_half([-180, -178], variables=["sst", "u10", "v10", "msl"]).to_netcdf(tmp_path / "a" / "x4.nc")

    halves = load_halves(tmp_path)

    assert list(halves["west"]["longitude"].values) == [176, 178, 180]
    assert list(halves["east"]["longitude"].values) == [-180, -178]
    for half in halves.values():
        assert list(half["date"].values) == list(DATES.values)  # 06:00 and 00:00 now line up
        assert set(half.data_vars) == {"sst", "u10", "v10", "msl", "tp"}


def to_halves(west, east):
    rename = {"valid_time": "date"}
    return west.rename(rename), east.rename(rename)


def test_join_uses_0_to_360_and_keeps_180_once():
    west, east = to_halves(make_half([176, 178, 180]), make_half([-180, -178, -176]))
    grid = join_halves(west, east)

    assert list(grid["longitude"].values) == [176, 178, 180, 182, 184]
    assert float(grid["sst"].sel(longitude=182).isel(date=0, latitude=0)) == 182


def test_join_checks_the_180_column_in_every_month():
    west, east = to_halves(make_half([176, 178, 180]), make_half([-180, -178]))
    east["msl"].loc[{"date": DATES[-1], "longitude": -180}] += 1  # last month only

    with pytest.raises(ValueError, match="180"):
        join_halves(west, east)


def test_join_rejects_different_months():
    west, east = to_halves(make_half([176, 178, 180]), make_half([-180, -178]))
    east = east.assign_coords(date=DATES + pd.DateOffset(months=1))

    with pytest.raises(ValueError, match="date"):
        join_halves(west, east)


def test_box_mean_weights_by_cos_latitude_and_skips_land():
    field = xr.DataArray(
        [[[1.0, np.nan], [3.0, 3.0]]],  # one month; the NaN is a land cell
        dims=("date", "latitude", "longitude"),
        coords={"date": DATES[:1], "latitude": [60.0, 0.0], "longitude": [10.0, 20.0]},
    )
    # Weights: cos(60) = 0.5 for the one sea cell up north, cos(0) = 1 for both cells at 0.
    expected = (0.5 * 1 + 1 * 3 + 1 * 3) / (0.5 + 1 + 1)
    assert box_mean(field, -90, 90, 0, 360).iloc[0] == pytest.approx(expected)


def make_raw_table(first_year=1950, last_year=2020):
    """Raw values that rise each year, then jump by 100 after 2008."""
    dates = pd.date_range(f"{first_year}-01-01", f"{last_year}-12-01", freq="MS")
    trend = (dates.year - first_year) + dates.month / 100 + np.where(dates.year > 2008, 100, 0)
    return pd.DataFrame({"date": dates, **{column: trend for column in RAW_COLUMNS}})


@pytest.mark.parametrize("base_first_year", [1950, 1979])
def test_anomalies_use_only_the_base_years(base_first_year):
    table = add_anomalies(make_raw_table(), base_first_year=base_first_year)
    base = table[table["date"].dt.year.between(base_first_year, 2008)]

    # Mean zero for every calendar month in the base period.
    monthly_means = base.groupby(base["date"].dt.month)[FEATURE_COLUMNS].mean()
    assert np.allclose(monthly_means, 0)

    # Changing values after 2008 changes nothing before (no leak from validation or test).
    changed = make_raw_table()
    changed.loc[changed["date"].dt.year > 2008, RAW_COLUMNS] += 50
    again = add_anomalies(changed, base_first_year=base_first_year)
    before = table["date"].dt.year <= 2008
    assert np.allclose(table.loc[before, FEATURE_COLUMNS], again.loc[before, FEATURE_COLUMNS])


def test_preliminary_flag_and_tp_in_mm_per_day():
    lats = np.arange(30.0, -30.5, -5.0)
    lons = np.arange(120.0, 290.5, 5.0)
    dates = pd.date_range("1950-01-01", "2009-12-01", freq="MS")
    shape = (len(dates), len(lats), len(lons))
    expver = ["0001"] * (len(dates) - 2) + ["0005"] * 2
    grid = xr.Dataset(
        {name: (("date", "latitude", "longitude"), np.ones(shape)) for name in ("sst", "u10", "v10", "msl")}
        | {"tp": (("date", "latitude", "longitude"), np.full(shape, 0.004))},  # metres per day
        coords={"date": dates, "latitude": lats, "longitude": lons, "expver": ("date", expver)},
    )

    table = build_era5_monthly(grid)

    assert table["preliminary"].tolist() == [False] * (len(dates) - 2) + [True, True]
    assert np.allclose(table["tp_central_mm_day"], 4.0)
