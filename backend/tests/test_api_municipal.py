import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.layer2 import municipal_map
from app.layer2.features import load_lookup
from main import app
from tests.test_api_layer2 import saved_models_exist

client = TestClient(app)
KALAYAAN = "1705321000"  # 0 km², far out at sea: the only municipality with no rain value


def test_municipal_rows_use_pagasa_bands_and_null_for_no_value():
    rain = pd.DataFrame({
        "adm3_psgc": ["0000000001", "0000000002", "0000000003", "0000000004", "1705300000"],
        "map_psgc": ["0102800000", "0102800000", "0102800000", "1303900000", "1705300000"],
        "year": [2025, 2025, 2025, 2025, None],  # the last one is like Kalayaan: no rain at all
        "quarter": [4, 4, 4, 4, None],
        "rain_pct_of_normal": [40.04, 80.0, 80.06, 300.0, None],
    })
    lookup = pd.DataFrame({"map_psgc": ["102800000", "1303900000", "1705300000"],
                           "crop_name": ["Ilocos Norte", None, "Palawan"]})
    rows = {row["adm3_psgc"]: row for row in municipal_map.municipal_rows(rain, lookup, 2025, 4)}
    assert len(rows) == 5
    assert (rows["0000000001"]["rain_pct"], rows["0000000001"]["colour"]) == (40.0, "red")  # rounded first
    assert rows["0000000002"]["colour"] == "yellow"
    assert (rows["0000000003"]["rain_pct"], rows["0000000003"]["colour"]) == (80.1, "green")
    assert rows["0000000001"]["province"] == "Ilocos Norte"
    assert rows["0000000004"]["province"] is None  # NCR has no crop province
    assert rows["1705300000"]["rain_pct"] is None and rows["1705300000"]["colour"] == "grey"


def test_prediction_view_is_rejected_with_a_pointer_to_the_province_map():
    response = client.get("/api/municipal_map", params={"quarter": "2026 Q4", "view": "prediction"})
    assert response.status_code == 422 and "/api/map" in response.json()["detail"]


def test_missing_municipal_shapes_give_503(monkeypatch, tmp_path):
    monkeypatch.setattr(municipal_map, "MUNICIPAL_DIR", tmp_path)
    assert client.get("/api/municipal_shapes").status_code == 503


@pytest.fixture
def real_files():
    if not saved_models_exist() or not municipal_map.MUNICIPAL_RAIN_PATH.exists():
        pytest.skip("saved models or municipal rain are missing: run both train commands "
                    "and python -m app.layer2.municipal_rain")


def test_unknown_quarter_is_422_and_missing_rain_file_is_503(real_files, monkeypatch, tmp_path):
    assert client.get("/api/municipal_map", params={"quarter": "1999 Q1", "view": "normal"}).status_code == 422
    monkeypatch.setattr(municipal_map, "MUNICIPAL_RAIN_PATH", tmp_path / "municipal_rain_quarterly.csv")
    response = client.get("/api/municipal_map", params={"quarter": "2026 Q4", "view": "normal"})
    assert response.status_code == 503 and "app.layer2.municipal_rain" in response.json()["detail"]


def test_municipal_shapes_and_map_match(real_files):
    features = client.get("/api/municipal_shapes").json()["features"]
    codes = [feature["properties"]["adm3_psgc"] for feature in features]
    assert len(features) == 1642 and len(set(codes)) == 1642 and all(len(code) == 10 for code in codes)
    provinces = {feature["properties"]["map_psgc"] for feature in features}
    assert provinces == set(load_lookup()["map_psgc"].str.zfill(10))  # every province shape has municipalities

    province_map = {entry["quarter"]: entry for entry in client.get("/api/map").json()}
    for quarter, entry in province_map.items():
        for view in municipal_map.MUNICIPAL_VIEWS:
            body = client.get("/api/municipal_map", params={"quarter": quarter, "view": view}).json()
            assert body["year"] == entry["views"][view]["year"]  # same year as the province map
            rows = {row["adm3_psgc"]: row for row in body["municipalities"]}
            assert set(rows) == set(codes)
            no_value = [code for code, row in rows.items() if row["rain_pct"] is None]
            assert no_value == [KALAYAAN] and rows[KALAYAAN]["colour"] == "grey"
