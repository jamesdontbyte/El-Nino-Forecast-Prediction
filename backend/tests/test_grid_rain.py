import numpy as np
import pandas as pd
import xarray as xr

from app.layer2.grid_rain import pixels_inside, quarterly_rain

LATS = np.arange(0.5, 5)  # pixel centres 0.5 .. 4.5
LONS = np.arange(0.5, 5)


def square(low, high):
    return [[low, low], [high, low], [high, high], [low, high], [low, low]]


def test_pixels_inside_skips_holes_and_joins_multipolygon_parts():
    with_hole = {"type": "Polygon", "coordinates": [square(0, 4), square(1, 2)]}
    mask = pixels_inside(with_hole, LATS, LONS)
    assert mask.sum() == 15  # 16 centres in the 4 x 4 square, minus the one inside the hole
    assert not mask[1, 1]

    two_parts = {"type": "MultiPolygon", "coordinates": [[square(0, 1)], [square(4, 5)]]}
    assert pixels_inside(two_parts, LATS, LONS).sum() == 2


def test_quarterly_rain_averages_pixels_ignores_sea_and_drops_incomplete_quarters():
    times = pd.date_range("2020-01-01", periods=4, freq="MS")  # Jan to Apr: Q1 complete, Q2 not
    values = np.full((4, 1, 3), 10.0)
    values[:, 0, 1] = 20.0
    values[:, 0, 2] = np.nan  # a sea pixel
    grid = xr.DataArray(values, coords={"time": times, "latitude": [0.5], "longitude": [0.5, 1.5, 2.5]},
                        dims=["time", "latitude", "longitude"])
    result = quarterly_rain(grid, np.array([[True, True, True]]))
    assert result[["year", "quarter"]].values.tolist() == [[2020, 1]]
    assert result["rain_mm"].iloc[0] == 45.0  # mean 15 mm a month, 3 months
