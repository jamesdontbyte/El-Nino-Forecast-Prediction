import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.data import load_crops, load_rainfall
from app.data.load_crops import load_crop

LOOKUP_PATH = Path(load_crops.__file__).with_name("province_lookup.csv")
RAW_DIR = load_crops.RAW_DIR


def write_psa(path, rows):
    """Write a tiny PSA-style file: title, blank line, header, then rows of
    (crop_type, location, 2020 Q1 value, 2020 Q2 value). Values are strings like "..".
    """
    header = '"Ecosystem/Croptype";"Geolocation";"2020 Quarter 1";"2020 Quarter 2";"2020 Annual"'
    lines = ['"Title"', "", header]
    lines += [f'"{c}";"{loc}";"{q1}";"{q2}";".."' for c, loc, q1, q2 in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def crop_table(tmp_path, area_rows, production_rows):
    area = write_psa(tmp_path / "area.csv", area_rows)
    production = write_psa(tmp_path / "production.csv", production_rows)
    return load_crop(area, production).set_index(["province", "quarter"])


def test_crop_cleaning_rules(tmp_path):
    rows_area = [
        ("Palay", "PHILIPPINES", "999", "999"),
        ("Palay", "..REGION XI (DAVAO REGION)", "999", "999"),
        ("Palay", "....Negros Occidental", "100", ".."),     # old row, Q1 only
        ("Palay", "....Negros Occidental a/", "..", "200"),  # new row, Q2 only
        ("Palay", "....Davao del Sur", "100", "0.00"),
        ("Palay", "....City of Davao", "300", ".."),
        ("Palay", "....Davao Occidental", "100", ".."),
        ("Palay", "....Maguindanao del Sur", "50", "50"),
        ("Palay", "....Maguindanao del Norte", "50", ".."),
        ("Palay", "....Sulu", "10", ".."),
        ("Palay", "....Sulu c/", "..", "20"),
        ("Palay", "....Tawi-tawi", "..", ".."),
    ]
    rows_production = [
        ("Palay", "PHILIPPINES", "999", "999"),
        ("Palay", "..REGION XI (DAVAO REGION)", "999", "999"),
        ("Palay", "....Negros Occidental", "400", ".."),
        ("Palay", "....Negros Occidental a/", "..", "600"),
        ("Palay", "....Davao del Sur", "100", "5"),
        ("Palay", "....City of Davao", "1500", ".."),
        ("Palay", "....Davao Occidental", "400", ".."),
        ("Palay", "....Maguindanao del Sur", "100", "100"),
        ("Palay", "....Maguindanao del Norte", "300", ".."),
        ("Palay", "....Sulu", "20", ".."),
        ("Palay", "....Sulu c/", "..", "60"),
        ("Palay", "....Tawi-tawi", "..", ".."),
    ]
    table = crop_table(tmp_path, rows_area, rows_production)

    # Region and national rows are not used; merged and renamed rows are gone.
    assert set(table.index.get_level_values("province")) == {
        "Negros Occidental", "Davao del Sur", "Maguindanao", "Sulu", "Tawi-Tawi",
    }

    # Negros: the old row and the a/ row form one series.
    assert table.loc[("Negros Occidental", 1), "yield_t_per_ha"] == 4.0
    assert table.loc[("Negros Occidental", 2), "yield_t_per_ha"] == 3.0

    # Davao del Sur + City of Davao + Davao Occidental are summed before yield:
    # (100 + 1500 + 400) / (100 + 300 + 100) = 4.0, not the mean of 1, 5 and 4.
    assert table.loc[("Davao del Sur", 1), "area_ha"] == 500
    assert table.loc[("Davao del Sur", 1), "yield_t_per_ha"] == 4.0

    # Maguindanao del Norte and del Sur are merged.
    assert table.loc[("Maguindanao", 1), "yield_t_per_ha"] == 4.0
    assert table.loc[("Maguindanao", 2), "yield_t_per_ha"] == 2.0

    # Sulu c/ continues Sulu (data only after the region move).
    assert table.loc[("Sulu", 1), "yield_t_per_ha"] == 2.0
    assert table.loc[("Sulu", 2), "yield_t_per_ha"] == 3.0

    # Zero area and missing area give a missing yield, not zero.
    assert np.isnan(table.loc[("Davao del Sur", 2), "yield_t_per_ha"])
    assert np.isnan(table.loc[("Tawi-Tawi", 1), "area_ha"])
    assert np.isnan(table.loc[("Tawi-Tawi", 1), "yield_t_per_ha"])


def test_unknown_footnote_is_an_error(tmp_path):
    rows = [("Palay", "....Some Province z/", "1", "1")]
    with pytest.raises(ValueError, match="Unknown footnoted rows"):
        crop_table(tmp_path, rows, rows)


def test_rainfall_rule_a_and_incomplete_quarter(tmp_path):
    # Q1 2020 is complete (9 ten-day rows); Q2 2020 has only 3 rows.
    q1 = pd.date_range("2020-01-01", periods=3, freq="MS").repeat(3) + pd.to_timedelta(
        [0, 10, 20] * 3, unit="D")
    q2 = pd.to_datetime(["2020-04-01", "2020-04-11", "2020-04-21"])
    dates = q1.append(q2)
    rain = pd.DataFrame({
        "date": dates, "adm_level": 2, "PCODE": "PH01028",
        "rfh": [10.0] * 9 + [5.0] * 3, "rfh_avg": [20.0] * 9 + [5.0] * 3, "version": "final",
    })
    regions = rain.assign(adm_level=1, PCODE="PH01")  # region rows must be ignored
    path = tmp_path / "rain.csv"
    pd.concat([rain, regions]).to_csv(path, index=False)

    table = load_rainfall.load_rainfall(path)

    assert len(table) == 1
    row = table.iloc[0]
    assert (row["pcode"], row["year"], row["quarter"]) == ("PH01028", 2020, 1)
    # Rule A: total over normal, 90 / 180 * 100.
    assert row["rain_mm"] == 90 and row["normal_mm"] == 180
    assert row["rain_pct_of_normal"] == 50.0


def read_lookup():
    return pd.read_csv(LOOKUP_PATH, dtype=str, keep_default_na=False)


def test_lookup_is_consistent():
    lookup = read_lookup()
    assert not lookup["map_psgc"].duplicated().any()
    assert (lookup["map_psgc"].str[2:5] == lookup["prov3"]).all()
    # Each rainfall code belongs to exactly one shape with the same province part.
    # Other shapes may share it (merged provinces, NCR districts).
    with_rain = lookup[lookup["rain_pcode"] != ""]
    own_shape = with_rain["rain_pcode"].str[4:] == with_rain["prov3"]
    assert with_rain[own_shape]["rain_pcode"].is_unique
    assert set(with_rain[own_shape]["rain_pcode"]) == set(with_rain["rain_pcode"])


def test_lookup_covers_every_source():
    if not RAW_DIR.exists():
        pytest.skip("data/raw/philippines is missing (data is gitignored)")
    lookup = read_lookup()

    crops = load_crops.load_crops()
    assert set(crops["province"]) == set(lookup["crop_name"]) - {""}

    rain = load_rainfall.load_rainfall()
    assert set(rain["pcode"]) == set(lookup["rain_pcode"]) - {""}

    shapes = set()
    for path in (RAW_DIR / "regions" / "medres").glob("*.json"):
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            shapes.add(str(int(feature["properties"]["adm2_psgc"])).zfill(10))
    assert shapes == set(lookup["map_psgc"])
