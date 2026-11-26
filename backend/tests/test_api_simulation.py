import pytest
from fastapi.testclient import TestClient

from app.simulation.simulate import IRRIGATION_GAIN_NOTE
from main import app
from tests.test_api_layer2 import saved_models_exist

client = TestClient(app)

ANTIQUE = {"province": "Antique", "crop": "Palay", "irrigation": True, "switching": True}


@pytest.mark.parametrize("bad", [
    {"province": "Atlantis"},
    {"crop": "Wheat"},
    {"pump_share": -0.1},
    {"pump_share": 1.5},
    {"switch_share": 2},
    {"irrigation_gain": -1},
    {"irrigation_gain": 10.5},
    {"irrigation_gain": "nan"},
])
def test_bad_input_is_422(bad):
    # Validation runs before any file is read, so this needs no saved models.
    assert client.get("/api/simulate", params=ANTIQUE | bad).status_code == 422


@pytest.fixture
def real_files():
    if not saved_models_exist():
        pytest.skip("saved models are missing: run both train commands")


def get_ok(params: dict) -> dict:
    response = client.get("/api/simulate", params=params)
    if response.status_code == 503:
        pytest.skip(response.json()["detail"])
    assert response.status_code == 200
    return response.json()


def test_antique_palay_shape_and_policy_effect(real_files):
    result = get_ok(ANTIQUE)
    assert result["province"] == "Antique" and len(result["quarters"]) == 2
    assert {"name": "irrigation_gain", "value": 3.6, "note": IRRIGATION_GAIN_NOTE} in result["assumptions"]
    q4, q1 = result["quarters"]
    assert q4["with"] == q4["without"] | {"pumps_given": 0, "switched": 0}  # already planted
    assert q1["with"]["pumps_given"] > 0
    # Q1's colour follows the live forecast, so check the rule for whichever colour it gets.
    if q1["colour"] == "red":
        assert q1["with"]["avg_yield_change_pct"] > q1["without"]["avg_yield_change_pct"]
    else:  # a pump adds nothing outside red quarters (layer3 spec)
        assert q1["with"]["avg_yield_change_pct"] == q1["without"]["avg_yield_change_pct"]


def test_default_shares_match_explicit_values(real_files):
    explicit = ANTIQUE | {"pump_share": 0.2, "switch_share": 0.1, "irrigation_gain": 3.6}
    assert get_ok(ANTIQUE) == get_ok(explicit)


def test_batanes_irrigated_palay_has_no_results(real_files):
    result = get_ok({"province": "Batanes", "crop": "Irrigated Palay", "irrigation": True, "switching": True})
    assert all(not q["enough_data"] and q["with"] is None for q in result["quarters"])
