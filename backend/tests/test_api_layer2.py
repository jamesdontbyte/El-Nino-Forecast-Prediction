import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.layer1_forecast import train as layer1_train
from app.layer2 import shapes
from app.layer2 import train as layer2_train
from app.layer2.features import load_lookup
from app.layer2.impact import CROP_TYPES, last_quarter_rain
from main import app

client = TestClient(app)


def saved_models_exist() -> bool:
    return all(path.exists() for path in [
        layer1_train.SAVED_MODELS_DIR / layer1_train.MODEL_FILE,
        layer2_train.SAVED_MODELS_DIR / layer2_train.RAIN_MODEL_FILE,
        layer2_train.SAVED_MODELS_DIR / layer2_train.YIELD_MODEL_FILE,
    ])


def test_options_lists_provinces_and_crops():
    options = client.get("/api/options").json()
    assert len(options["provinces"]) == 80 and all(options["provinces"])
    assert options["crops"] == CROP_TYPES


def test_unknown_province_or_crop_is_422():
    assert client.get("/api/impact", params={"province": "Atlantis", "crop": "Palay"}).status_code == 422
    assert client.get("/api/impact", params={"province": "Nueva Ecija", "crop": "Wheat"}).status_code == 422


def test_missing_models_give_503(monkeypatch, tmp_path):
    # Both layers keep their own copy of the folder, so both are pointed at an empty folder.
    monkeypatch.setattr(layer1_train, "SAVED_MODELS_DIR", tmp_path)
    monkeypatch.setattr(layer2_train, "SAVED_MODELS_DIR", tmp_path)
    for response in [client.get("/api/impact", params={"province": "Nueva Ecija", "crop": "Palay"}),
                     client.get("/api/map")]:
        assert response.status_code == 503
        assert "app.layer2.train" in response.json()["detail"]


def test_last_quarter_rain_is_observed_if_present_else_predicted():
    observed = pd.DataFrame({"year": [2026], "quarter": [3], "rain_pct_of_normal": [90.0]})
    predicted = pd.DataFrame({"year": [2026, 2027], "quarter": [4, 1], "rain_pct": [60.0, 40.0]})
    assert last_quarter_rain(observed, predicted, 2026, 4) == 90.0  # Q3 2026 was observed
    assert last_quarter_rain(observed, predicted, 2027, 1) == 60.0  # Q4 2026 is only predicted
    with pytest.raises(ValueError):
        last_quarter_rain(observed, predicted, 2026, 3)


@pytest.fixture
def real_files():
    if not saved_models_exist():
        pytest.skip("saved models are missing: run both train commands")


def test_map_route_with_real_files(real_files):
    response = client.get("/api/map")
    if response.status_code == 503:
        pytest.skip(response.json()["detail"])
    quarters = response.json()
    assert len(quarters) == 2
    for quarter in quarters:
        assert len(quarter["views"]) == 4
        assert all(len(view["shapes"]) == 88 for view in quarter["views"].values())


def test_impact_route_with_real_files(real_files):
    response = client.get("/api/impact", params={"province": "Nueva Ecija", "crop": "Palay"})
    if response.status_code == 503:
        pytest.skip(response.json()["detail"])
    body = response.json()
    assert body["models_used"]["yield"] == "departure_line"
    assert len(body["quarters"]) == 2
    for q in body["quarters"]:
        assert q["enough_data"] and math.isfinite(q["rain_pct"])
        expected = q["normal_yield_t_per_ha"] * (1 + q["yield_change_pct"] / 100)
        assert q["predicted_yield_t_per_ha"] == pytest.approx(expected, abs=0.01)


def test_thin_cell_has_no_yield(real_files):
    response = client.get("/api/impact", params={"province": "Batanes", "crop": "Irrigated Palay"})
    if response.status_code == 503:
        pytest.skip(response.json()["detail"])
    for q in response.json()["quarters"]:
        assert q["enough_data"] is False and q["yield_change_pct"] is None
        assert q["normal_yield_t_per_ha"] is None and q["predicted_yield_t_per_ha"] is None
        assert q["rain_pct"] is not None  # rainfall is still shown


def test_shapes_route_has_88_shapes_matching_the_map_codes():
    if not shapes.SHAPES_DIR.exists():
        pytest.skip("shape files are missing (data is gitignored)")
    response = client.get("/api/shapes", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    features = response.json()["features"]
    codes = [feature["properties"]["map_psgc"] for feature in features]
    assert len(features) == 88 and all(len(code) == 10 for code in codes)
    # /api/map takes its codes from the lookup, so matching the lookup means matching the map.
    assert set(codes) == set(load_lookup()["map_psgc"])
    assert all(feature["properties"]["name"] for feature in features)


def test_shape_coordinates_are_rounded_to_3_decimals():
    assert shapes.round_coordinates([[[120.571822, 17.786033], [1, 2.00049]]]) == [[[120.572, 17.786], [1, 2.0]]]


def test_missing_shape_files_give_503(monkeypatch, tmp_path):
    monkeypatch.setattr(shapes, "SHAPES_DIR", tmp_path)
    response = client.get("/api/shapes")
    assert response.status_code == 503
    assert "data file is missing" in response.json()["detail"]
