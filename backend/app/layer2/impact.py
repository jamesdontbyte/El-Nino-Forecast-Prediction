"""Layer 2 impact for one province and crop: rainfall and yield change per forecast quarter.

For each quarter the Layer 1 forecast covers:
- rain_pct: rainfall % of normal predicted by the saved rain model (and its dryness colour).
- yield_change_pct: predicted by the saved yield model from this and last quarter's rain % and ONI.
- normal_yield_t_per_ha: the straight line through the 10 previous years, extended one year.
- predicted_yield_t_per_ha: normal x (1 + change / 100).
When one of the 10 previous years has no yield, enough_data is false and the yield fields are null.

Needs the saved models: python -m app.layer1_forecast.train and python -m app.layer2.train.
"""

import joblib
import pandas as pd

from app.api.forecast import forecast_from_bundle
from app.data.load_crops import load_crops
from app.data.load_rainfall import load_rainfall
from app.layer1_forecast import train as layer1_train
from app.layer1_forecast.models import load_enso_monthly, load_era5_monthly
from app.layer2 import train as layer2_train
from app.layer2.features import (
    RAIN_TARGET,
    crop_pcodes,
    load_lookup,
    normal_yield,
    oni_with_previous,
)
from app.layer2.map_output import (
    PAST_EVENTS,
    combined_oni,
    dryness_colour,
    forecast_quarters,
    predicted_rain,
)

CROP_TYPES = ["Irrigated Palay", "Rainfed Palay", "Palay", "White Corn", "Yellow Corn", "Corn"]


def province_names(lookup: pd.DataFrame) -> list[str]:
    """Crop provinces from the lookup. Merged provinces appear once; NCR, Isabela and SGA have no name."""
    return sorted(crop_pcodes(lookup)["crop_name"].unique())


def previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def last_quarter_rain(observed: pd.DataFrame, predicted: pd.DataFrame, year: int, quarter: int) -> float:
    """Last quarter's rain %: observed if that quarter has rainfall data, otherwise predicted.

    `observed` has year, quarter, rain_pct_of_normal for one province; `predicted` has year,
    quarter, rain_pct for the forecast quarters of the same province.
    """
    prev_year, prev_quarter = previous_quarter(year, quarter)
    for table, column in [(observed, RAIN_TARGET), (predicted, "rain_pct")]:
        row = table[(table["year"] == prev_year) & (table["quarter"] == prev_quarter)]
        if not row.empty:
            return float(row[column].iloc[0])
    raise ValueError(f"No rainfall, observed or predicted, for {prev_year} Q{prev_quarter}.")


def cell_normals(crops: pd.DataFrame, province: str, crop: str, quarters: pd.DataFrame) -> dict:
    """Normal yield (t/ha) per forecast (year, quarter) for one province and crop. Missing means not enough data."""
    cell = crops[(crops["province"] == province) & (crops["crop_type"] == crop)]
    have = set(zip(cell["year"], cell["quarter"]))
    # Forecast quarters not in the crop table yet (for example 2027 Q1) get an empty-yield row.
    extra = [{"crop_type": crop, "province": province, "year": y, "quarter": q, "yield_t_per_ha": float("nan")}
             for y, q in zip(quarters["year"], quarters["quarter"]) if (y, q) not in have]
    cell = pd.concat([cell, pd.DataFrame(extra)], ignore_index=True)  # unique index for normal_yield
    cell = cell.assign(normal=normal_yield(cell))
    return {(int(r.year), int(r.quarter)): r.normal for r in cell.itertuples()}


def impact_entries(quarter_rows: pd.DataFrame, observed: pd.DataFrame, normals: dict, yield_model) -> list[dict]:
    """One entry per row of `quarter_rows` (year, quarter, oni, oni_prev, rain_pct), in its order.

    `observed` is the province's observed rainfall, used for last quarter's rain when it exists.
    """
    result = []
    for q in quarter_rows.itertuples():
        rain_pct = float(q.rain_pct)
        entry = {
            "quarter": f"{q.year} Q{q.quarter}",
            "oni": round(float(q.oni), 2),
            "oni_prev": round(float(q.oni_prev), 2),
            "rain_pct": None if pd.isna(rain_pct) else round(rain_pct, 1),
            "colour": dryness_colour(round(rain_pct, 1)),
            "enough_data": False,
            "yield_change_pct": None,
            "normal_yield_t_per_ha": None,
            "predicted_yield_t_per_ha": None,
        }
        normal = normals.get((int(q.year), int(q.quarter)))
        if normal is None or pd.isna(normal) or normal <= 0 or pd.isna(rain_pct):
            result.append(entry)
            continue
        rain_prev = last_quarter_rain(observed, quarter_rows, int(q.year), int(q.quarter))
        # XGBoost accepts a missing rain % silently, so a quarter without rain is never predicted.
        if not pd.isna(rain_prev):
            inputs = pd.DataFrame([{
                "rain_pct": rain_pct,  # unrounded: rounding is only for display
                "rain_pct_prev": rain_prev,
                "oni": float(q.oni), "oni_prev": float(q.oni_prev),
            }])
            change = float(pd.Series(yield_model.predict(inputs)).clip(-100, 100).iloc[0])  # as in training
            entry.update({
                "enough_data": True,
                "yield_change_pct": round(change, 1),
                "normal_yield_t_per_ha": round(float(normal), 2),
                "predicted_yield_t_per_ha": round(float(normal) * (1 + change / 100), 2),
            })
        result.append(entry)
    return result


def province_impact(province: str, crop: str, enso: pd.DataFrame, forecast_series: list[dict],
                    rain: pd.DataFrame, crops: pd.DataFrame, lookup: pd.DataFrame,
                    rain_model, yield_model) -> list[dict]:
    """One entry per forecast quarter for the chosen province and crop."""
    pcode = crop_pcodes(lookup).set_index("crop_name").loc[province, "rain_pcode"]
    quarters = forecast_quarters(enso, combined_oni(enso, forecast_series))
    predicted = predicted_rain(quarters, [pcode], rain_model)
    observed = rain[rain["pcode"] == pcode]
    return impact_entries(predicted, observed, cell_normals(crops, province, crop, quarters), yield_model)


def replay_impact(province: str, crop: str, event: str, enso: pd.DataFrame, rain: pd.DataFrame,
                  crops: pd.DataFrame, lookup: pd.DataFrame, yield_model) -> list[dict]:
    """One entry per quarter of a past event (PAST_EVENTS), from observed rain and ONI, in time order."""
    pcode = crop_pcodes(lookup).set_index("crop_name").loc[province, "rain_pcode"]
    quarters = pd.DataFrame(sorted((year, quarter) for quarter, year in PAST_EVENTS[event].items()),
                            columns=["year", "quarter"])
    quarters = quarters.merge(oni_with_previous(enso), on=["year", "quarter"], how="left")
    if quarters[["oni", "oni_prev"]].isna().any().any():
        raise ValueError(f"Replay quarters need observed ONI for this and last quarter:\n{quarters}")
    observed = rain[rain["pcode"] == pcode]
    rows = quarters.merge(observed[["year", "quarter", RAIN_TARGET]], on=["year", "quarter"], how="left")
    rows = rows.rename(columns={RAIN_TARGET: "rain_pct"})
    return impact_entries(rows, observed, cell_normals(crops, province, crop, quarters), yield_model)


def load_impact(province: str, crop: str) -> dict:
    """Impact for one province and crop from the saved models and the data files."""
    enso = load_enso_monthly()
    forecast = forecast_from_bundle(layer1_train.load_model(layer1_train.SAVED_MODELS_DIR), enso,
                                    load_era5_monthly())
    rain_saved = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.RAIN_MODEL_FILE)
    yield_saved = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.YIELD_MODEL_FILE)
    quarters = province_impact(province, crop, enso, forecast["forecast_series"], load_rainfall(),
                               load_crops(), load_lookup(), rain_saved["model"], yield_saved["model"])
    return {
        "province": province,
        "crop": crop,
        "models_used": {"rain": rain_saved["model_name"], "yield": yield_saved["model_name"]},
        "quarters": quarters,
    }
