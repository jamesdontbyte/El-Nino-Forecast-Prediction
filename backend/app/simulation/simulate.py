"""Layer 3 policy simulation: El Nino outcome without and with the chosen policies.

Rule-based, no machine learning (specs/layer3-simulation.md):
- About 100 farmer agents get a crop type from the chosen crop (Palay: irrigated or rainfed by
  the province's irrigated share). A fixed seed makes every run give the same result.
- A farmer's yield change % = the Layer 2 change for the quarter + the gap for its crop type
  and the rain colour (CROP_GAPS). t/ha = that crop type's normal x (1 + change / 100).
- The local government gives pumps to rainfed palay farmers and, in red quarters, advises
  some of the rest to switch to corn. Both act only in POLICY_QUARTER.
- "without" and "with" use the same farmers. Only the policies differ.

The output is a set of possible scenarios, not certain outcomes.
"""

import math

import joblib
import numpy as np
import pandas as pd

from app.api.forecast import forecast_from_bundle
from app.data.load_crops import load_crops
from app.data.load_rainfall import load_rainfall
from app.layer1_forecast import train as layer1_train
from app.layer1_forecast.models import load_enso_monthly, load_era5_monthly
from app.layer2 import train as layer2_train
from app.layer2.features import load_lookup
from app.layer2.impact import province_impact

# Median yield change minus the Palay median in past El Nino quarters, in percentage points
# (spec section 4). Grey (no rain data) has no gap.
CROP_GAPS = {
    "Palay": {"red": 0.0, "yellow": 0.0, "green": 0.0},
    "Irrigated Palay": {"red": 0.4, "yellow": 0.2, "green": 0.1},
    "Rainfed Palay": {"red": -3.2, "yellow": -0.9, "green": -0.2},
    "Corn": {"red": -3.1, "yellow": -1.3, "green": -0.8},
    "White Corn": {"red": -4.1, "yellow": -0.7, "green": -1.3},
    "Yellow Corn": {"red": -2.8, "yellow": -1.8, "green": -0.7},
}

FARMERS = 100
SEED = 42
PUMP_SHARE = 0.2
SWITCH_SHARE = 0.1
IRRIGATION_GAIN = 3.6
# Decided timing: the 2026 Q4 crop is already planted. When the forecast quarters move,
# this needs a decision (spec section 10, open items).
POLICY_QUARTER = "2027 Q1"

IRRIGATION_GAIN_NOTE = "estimated from two strong El Niños, not statistically firm"
DISCLAIMER = "These are possible scenarios, not certain outcomes."

IRRIGATED = "Irrigated Palay"
RAINFED = "Rainfed Palay"
PUMPED = "Rainfed Palay with pump"
SWITCHED = "Corn (switched)"
POLICY_CROPS = ["Palay", RAINFED]  # crops that have rainfed palay farmers
GROUP_ORDER = [IRRIGATED, RAINFED, PUMPED, SWITCHED, "Corn", "White Corn", "Yellow Corn"]


def gap(crop_type: str, colour: str) -> float:
    return CROP_GAPS[crop_type].get(colour, 0.0)


def round_half_up(x: float) -> int:
    """Python's round() sends 2.5 to 2 (banker's rounding); the spec means plain rounding."""
    return math.floor(x + 0.5)


def irrigated_share(crops: pd.DataFrame, province: str) -> tuple[float, int]:
    """Irrigated palay area / total palay area in the latest complete year, and that year.

    A year counts when both Irrigated and Rainfed Palay have area in all 4 quarters and the
    total is above 0. A province with no rainfed area gets 1.0.
    """
    rows = crops[(crops["province"] == province) & crops["crop_type"].isin([IRRIGATED, RAINFED])]
    rows = rows.dropna(subset=["area_ha"])
    quarters_with_area = rows.groupby(["year", "crop_type"])["quarter"].nunique().unstack()
    area = rows.groupby(["year", "crop_type"])["area_ha"].sum().unstack()
    quarters_with_area = quarters_with_area.reindex(columns=[IRRIGATED, RAINFED])
    area = area.reindex(columns=[IRRIGATED, RAINFED])
    complete = quarters_with_area.eq(4).all(axis=1) & (area.sum(axis=1) > 0)
    years = complete[complete].index
    if len(years) == 0:
        raise ValueError(f"No year with palay area in all 4 quarters for {province}.")
    year = int(years.max())
    return float(area.loc[year, IRRIGATED] / area.loc[year].sum()), year


def make_farmers(crop: str, irrigated_share: float | None, farmers: int, seed: int) -> list[str]:
    """One crop type per farmer. Only Palay mixes types, by the province's irrigated share."""
    if crop != "Palay":
        return [crop] * farmers
    draws = np.random.default_rng(seed).random(farmers)
    return [IRRIGATED if draw < irrigated_share else RAINFED for draw in draws]


def quarter_of(impacts: dict, crop_type: str, index: int) -> dict | None:
    """The Layer 2 entry of a crop type for the same quarter, or None when there is no data."""
    entries = impacts.get(crop_type)
    if not entries or index >= len(entries) or not entries[index]["enough_data"]:
        return None
    return entries[index]


def side_result(changes: list[float], groups: list[str], normals: dict) -> dict:
    """Average change over all farmers, plus one row per non-empty group.

    t/ha is per group only: palay and corn t/ha are never averaged together.
    """
    rows = []
    for group in GROUP_ORDER:
        members = [change for change, name in zip(changes, groups) if name == group]
        if not members:
            continue
        change = members[0]  # every farmer in a group has the same change
        normal = normals.get(group)
        rows.append({
            "group": group,
            "farmers": len(members),
            "yield_change_pct": round(change, 1),
            "yield_t_per_ha": None if normal is None else round(normal * (1 + change / 100), 2),
        })
    return {"avg_yield_change_pct": round(float(np.mean(changes)), 1), "groups": rows}


def run(crop: str, impacts: dict, irrigated_share: float | None, irrigation: bool, switching: bool,
        pump_share: float = PUMP_SHARE, switch_share: float = SWITCH_SHARE,
        irrigation_gain: float = IRRIGATION_GAIN, farmers: int = FARMERS, seed: int = SEED) -> dict:
    """Simulate every forecast quarter without and with the chosen policies.

    `impacts` maps crop type -> Layer 2 quarter entries (province_impact), with the chosen crop
    and, when available, Irrigated Palay, Rainfed Palay and Corn. Quarters line up by position.
    """
    farmer_types = make_farmers(crop, irrigated_share, farmers, seed)

    # One fixed pick order: a bigger share adds farmers to the list, it never reshuffles who is picked.
    pick_order = np.random.default_rng(seed + 1).permutation(farmers)
    rainfed = [int(i) for i in pick_order if farmer_types[i] == RAINFED]
    n_pumps = min(round_half_up(pump_share * len(rainfed)), len(rainfed)) if irrigation else 0
    pump_farmers = set(rainfed[:n_pumps])
    # Irrigation goes first; switchers come from the rainfed farmers left without a pump.
    switch_farmers = set(rainfed[n_pumps:][:round_half_up(switch_share * len(rainfed))])

    quarters = []
    for index, entry in enumerate(impacts[crop]):
        result = {"quarter": entry["quarter"], "rain_pct": entry["rain_pct"], "colour": entry["colour"],
                  "enough_data": entry["enough_data"]}
        if not entry["enough_data"]:
            result.update({"without": None, "with": None,
                           "notes": [f"Not enough yield data for {crop} in this quarter, so no results."]})
            quarters.append(result)
            continue

        base = entry["yield_change_pct"]
        colour = entry["colour"]
        normals = {}
        for crop_type in [crop, IRRIGATED, RAINFED, "Corn"]:
            data = quarter_of(impacts, crop_type, index)
            normals[crop_type] = None if data is None else data["normal_yield_t_per_ha"]
        normals[PUMPED] = normals[RAINFED]  # a pump in one season does not give the irrigated normal
        normals[SWITCHED] = normals["Corn"]

        without_changes = [base + gap(t, colour) for t in farmer_types]
        with_changes = list(without_changes)
        with_groups = list(farmer_types)
        notes = []

        policy_applies = crop in POLICY_CROPS and len(rainfed) > 0
        in_policy_quarter = entry["quarter"] == POLICY_QUARTER
        chosen = [name for name, on in [("Irrigation support", irrigation), ("Crop switching", switching)] if on]
        for name in chosen:
            if crop not in POLICY_CROPS + [IRRIGATED]:
                notes.append(f"{name} did not apply: no policy applies to corn crops.")
            elif not policy_applies:
                notes.append(f"{name} did not apply: there are no rainfed palay farmers.")
            elif not in_policy_quarter:
                notes.append(f"{name} did not apply: the {entry['quarter']} crop is already planted. "
                             f"Policies act only in {POLICY_QUARTER}.")

        pumps_given = 0
        switched = 0
        if policy_applies and in_policy_quarter:
            if irrigation:
                pumps_given = len(pump_farmers)
                for i in pump_farmers:
                    with_groups[i] = PUMPED
                    if colour == "red":
                        with_changes[i] = base + gap(RAINFED, colour) + irrigation_gain
                if colour != "red":
                    notes.append(f"Pumps were given, but they add nothing in a {colour} quarter. "
                                 "The irrigation gain applies only in red quarters.")
            if switching:
                if colour != "red":
                    notes.append(f"Crop switching did not apply: it is advised only in red quarters, "
                                 f"and this quarter is {colour}.")
                elif normals["Corn"] is None:
                    notes.append("Crop switching was skipped: Corn has not enough yield data in this quarter.")
                else:
                    switched = len(switch_farmers)
                    for i in switch_farmers:
                        with_groups[i] = SWITCHED
                        with_changes[i] = base + gap("Corn", colour)

        result["without"] = side_result(without_changes, farmer_types, normals)
        result["with"] = side_result(with_changes, with_groups, normals) | {
            "pumps_given": pumps_given, "switched": switched}
        result["notes"] = notes
        quarters.append(result)

    return {
        "crop": crop,
        "policies": {"irrigation": irrigation, "switching": switching},
        "farmers": farmers,
        "seed": seed,
        "irrigated_share": None if crop != "Palay" else round(irrigated_share, 3),
        "pump_share": pump_share,
        "switch_share": switch_share,
        "irrigation_gain": irrigation_gain,
        "quarters": quarters,
        "assumptions": [
            {"name": "farmers", "value": farmers, "note": "stated assumption"},
            {"name": "pump_share", "value": pump_share, "note": "stated assumption"},
            {"name": "switch_share", "value": switch_share, "note": "stated assumption"},
            {"name": "irrigation_gain", "value": irrigation_gain, "note": IRRIGATION_GAIN_NOTE},
        ],
        "disclaimer": DISCLAIMER,
    }


def simulate(province: str, crop: str, irrigation: bool, switching: bool,
             pump_share: float = PUMP_SHARE, switch_share: float = SWITCH_SHARE,
             irrigation_gain: float = IRRIGATION_GAIN) -> dict:
    """Simulation for one province and crop from the saved models and data files (loaded once)."""
    enso = load_enso_monthly()
    forecast = forecast_from_bundle(layer1_train.load_model(layer1_train.SAVED_MODELS_DIR), enso,
                                    load_era5_monthly())
    rain_model = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.RAIN_MODEL_FILE)["model"]
    yield_model = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.YIELD_MODEL_FILE)["model"]
    rain, crops, lookup = load_rainfall(), load_crops(), load_lookup()

    impacts = {}
    for crop_type in dict.fromkeys([crop, IRRIGATED, RAINFED, "Corn"]):  # keeps order, drops duplicates
        impacts[crop_type] = province_impact(province, crop_type, enso, forecast["forecast_series"],
                                             rain, crops, lookup, rain_model, yield_model)
    share = irrigated_share(crops, province)[0] if crop == "Palay" else None
    return {"province": province} | run(crop, impacts, share, irrigation, switching,
                                        pump_share, switch_share, irrigation_gain)
