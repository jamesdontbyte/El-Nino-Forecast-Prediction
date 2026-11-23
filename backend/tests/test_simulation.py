import pandas as pd
import pytest

from app.simulation import simulate as sim

NORMALS = {"Palay": 4.0, "Irrigated Palay": 5.0, "Rainfed Palay": 3.0, "Corn": 2.0,
           "White Corn": 1.5, "Yellow Corn": 2.5}


def quarter(label: str, colour: str, change: float, normal: float, enough_data: bool = True) -> dict:
    """One hand-made Layer 2 quarter entry (the shape of province_impact)."""
    return {"quarter": label, "oni": 1.0, "oni_prev": 1.0, "rain_pct": 30.0, "colour": colour,
            "enough_data": enough_data,
            "yield_change_pct": change if enough_data else None,
            "normal_yield_t_per_ha": normal if enough_data else None,
            "predicted_yield_t_per_ha": normal * (1 + change / 100) if enough_data else None}


def impacts(q1_colour: str = "red", corn_data: bool = True, crop_data: bool = True) -> dict:
    """2026 Q4 (red) and 2027 Q1 for every crop type, with a -10% Layer 2 change."""
    result = {}
    for crop_type, normal in NORMALS.items():
        has_data = (corn_data or crop_type != "Corn") and crop_data
        result[crop_type] = [quarter("2026 Q4", "red", -10.0, normal),
                             quarter("2027 Q1", q1_colour, -10.0, normal, has_data)]
    return result


def q1(result: dict) -> dict:
    return result["quarters"][1]


def without_policy_info(side: dict) -> dict:
    return {key: side[key] for key in ["avg_yield_change_pct", "groups"]}


def test_no_policies_with_equals_without():
    result = sim.run("Palay", impacts(), 0.5, irrigation=False, switching=False)
    for q in result["quarters"]:
        assert without_policy_info(q["with"]) == q["without"]


def test_same_inputs_same_output():
    assert sim.run("Palay", impacts(), 0.5, True, True) == sim.run("Palay", impacts(), 0.5, True, True)


@pytest.mark.parametrize("changed", [{"pump_share": 0.5}, {"switch_share": 0.5}, {"irrigation_gain": 8.0}])
def test_changing_an_assumption_changes_the_result(changed):
    default = q1(sim.run("Palay", impacts(), 0.5, True, True))["with"]
    other = q1(sim.run("Palay", impacts(), 0.5, True, True, **changed))["with"]
    assert other != default


@pytest.mark.parametrize("colour", ["yellow", "green"])
def test_gain_changes_nothing_outside_red(colour):
    result = q1(sim.run("Palay", impacts(colour), 0.5, True, False))
    assert result["with"]["pumps_given"] > 0
    assert result["with"]["avg_yield_change_pct"] == result["without"]["avg_yield_change_pct"]
    no_gain = q1(sim.run("Palay", impacts(colour), 0.5, True, False, irrigation_gain=0.0))
    assert no_gain["with"] == result["with"]
    assert any("only in red" in note for note in result["notes"])


@pytest.mark.parametrize("crop", ["Corn", "White Corn", "Yellow Corn", "Irrigated Palay"])
def test_corn_and_irrigated_palay_ignore_policies(crop):
    result = q1(sim.run(crop, impacts(), None, True, True))
    assert without_policy_info(result["with"]) == result["without"]
    assert result["with"]["pumps_given"] == 0 and result["with"]["switched"] == 0
    assert len(result["notes"]) == 2


def test_2026_q4_same_with_and_without():
    first = sim.run("Palay", impacts(), 0.5, True, True)["quarters"][0]
    assert without_policy_info(first["with"]) == first["without"]
    assert "already planted" in first["notes"][0]


def test_switching_skipped_when_corn_has_no_data():
    result = q1(sim.run("Rainfed Palay", impacts(corn_data=False), None, False, True))
    assert result["with"]["switched"] == 0
    assert any("Corn has not enough" in note for note in result["notes"])


def test_pumped_farmer_keeps_rainfed_normal():
    groups = {g["group"]: g for g in q1(sim.run("Rainfed Palay", impacts(), None, True, False))["with"]["groups"]}
    pumped = groups["Rainfed Palay with pump"]
    change = -10.0 - 3.2 + 3.6
    assert pumped["yield_change_pct"] == round(change, 1)
    assert pumped["yield_t_per_ha"] == round(3.0 * (1 + change / 100), 2)


def test_both_on_pumps_first_then_switchers():
    result = q1(sim.run("Rainfed Palay", impacts(), None, True, True))["with"]
    assert (result["pumps_given"], result["switched"]) == (20, 10)
    counts = {g["group"]: g["farmers"] for g in result["groups"]}
    assert counts == {"Rainfed Palay": 70, "Rainfed Palay with pump": 20, "Corn (switched)": 10}

    capped = q1(sim.run("Rainfed Palay", impacts(), None, True, True, pump_share=0.95, switch_share=0.5))["with"]
    assert (capped["pumps_given"], capped["switched"]) == (95, 5)


def test_chosen_crop_without_data_has_no_results():
    result = q1(sim.run("Palay", impacts(crop_data=False), 0.5, True, True))
    assert result["enough_data"] is False and result["colour"] == "red"
    assert result["without"] is None and result["with"] is None


def crop_rows(province: str, crop_type: str, year: int, areas: list) -> list[dict]:
    return [{"crop_type": crop_type, "province": province, "year": year, "quarter": q + 1, "area_ha": a}
            for q, a in enumerate(areas)]


def test_irrigated_share_latest_complete_year():
    rows = (crop_rows("A", "Irrigated Palay", 2023, [10, 10, 10, 10])
            + crop_rows("A", "Rainfed Palay", 2023, [30, 30, 30, 30])
            + crop_rows("A", "Irrigated Palay", 2024, [20, 20, 20, 20])
            + crop_rows("A", "Rainfed Palay", 2024, [0, 0, 0, 0])
            + crop_rows("A", "Irrigated Palay", 2025, [5, 5, None, 5])  # incomplete, skipped
            + crop_rows("A", "Rainfed Palay", 2025, [5, 5, 5, 5]))
    crops = pd.DataFrame(rows)
    assert sim.irrigated_share(crops, "A") == (1.0, 2024)
    assert sim.irrigated_share(crops[crops["year"] == 2023], "A") == (0.25, 2023)
    with pytest.raises(ValueError, match="B"):
        sim.irrigated_share(crops, "B")


def test_gain_note_in_assumptions():
    assumptions = {a["name"]: a for a in sim.run("Palay", impacts(), 0.5, True, True)["assumptions"]}
    assert assumptions["irrigation_gain"]["note"] == sim.IRRIGATION_GAIN_NOTE
