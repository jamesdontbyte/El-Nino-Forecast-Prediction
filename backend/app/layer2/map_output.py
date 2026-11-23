"""Layer 2 map output: rainfall percent of normal and a dryness colour for every map shape.

For each quarter the Layer 1 forecast covers, four views (decisions in specs/layer2-impact.md):
- prediction: rainfall predicted by the saved rain model from the forecast ONI.
- normal: observed rainfall in the latest year whose same quarter was neutral.
- el_nino_2015_16 and el_nino_2023_24: observed rainfall for that quarter inside each event.

Colours use PAGASA's rainfall bands: red 40% of normal or less, yellow 80% or less,
otherwise green. Shapes with no rainfall (City of Isabela, Special Geographic Area) are grey.

Run from backend/:  python -m app.layer2.map_output   (prints colour counts per view)
Needs the saved models: python -m app.layer1_forecast.train and python -m app.layer2.train.
"""

import joblib
import pandas as pd

from app.api.forecast import forecast_from_bundle
from app.data.load_rainfall import load_rainfall
from app.layer1_forecast import train as layer1_train
from app.layer1_forecast.labels import find_events
from app.layer1_forecast.models import load_enso_monthly
from app.layer2 import train as layer2_train
from app.layer2.features import (
    RAIN_TARGET,
    add_previous_quarter,
    load_lookup,
    quarterly_oni,
)

RED_MAX = 40.0  # PAGASA "way below normal": 40% of normal or less
YELLOW_MAX = 80.0  # PAGASA "below normal": 41 to 80%
EVENT_MONTHS_NEEDED = 2  # decided: a quarter is El Nino (or La Nina) if 2 of its 3 months are in an event

# Which year's quarter falls inside each past event (decided). 2023-24 has no Q2 inside it.
PAST_EVENTS = {
    "el_nino_2015_16": {1: 2016, 2: 2016, 3: 2015, 4: 2015},
    "el_nino_2023_24": {1: 2024, 3: 2023, 4: 2023},
}


def dryness_colour(rain_pct: float | None) -> str:
    """PAGASA band colour. Pass the rounded value, so the colour matches the shown number."""
    if rain_pct is None or pd.isna(rain_pct):
        return "grey"
    if rain_pct <= RED_MAX:
        return "red"
    if rain_pct <= YELLOW_MAX:
        return "yellow"
    return "green"


def _event_months(monthly: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """True for months inside an event. An ongoing event runs to the last month of data."""
    last_month = monthly["date"].max()
    inside = pd.Series(False, index=monthly.index)
    for _, event in events.iterrows():
        end = last_month if pd.isna(event["end_month"]) else event["end_month"]
        inside |= monthly["date"].between(event["start_month"], end)
    return inside


def quarter_phase(enso: pd.DataFrame) -> pd.DataFrame:
    """El Nino, La Nina, Neutral or Mixed for each quarter with all 3 months observed.

    Uses observed ONI only: forecast months would stretch the ongoing event.
    La Nina events are found by running the El Nino rule on -ONI.
    """
    monthly = enso[["date", "oni"]].dropna().reset_index(drop=True)
    monthly = monthly.assign(
        year=monthly["date"].dt.year, quarter=monthly["date"].dt.quarter,
        el_nino=_event_months(monthly, find_events(monthly)),
        la_nina=_event_months(monthly, find_events(monthly.assign(oni=-monthly["oni"]))),
    )
    quarters = monthly.groupby(["year", "quarter"], as_index=False).agg(
        months=("oni", "size"), el_nino=("el_nino", "sum"), la_nina=("la_nina", "sum"))
    quarters = quarters[quarters["months"] == 3].copy()

    quarters["phase"] = "Mixed"  # touches an event with only one month
    quarters.loc[(quarters["el_nino"] == 0) & (quarters["la_nina"] == 0), "phase"] = "Neutral"
    quarters.loc[quarters["la_nina"] >= EVENT_MONTHS_NEEDED, "phase"] = "La Nina"
    quarters.loc[quarters["el_nino"] >= EVENT_MONTHS_NEEDED, "phase"] = "El Nino"  # checked first, so it wins
    return quarters[["year", "quarter", "phase"]].reset_index(drop=True)


def combined_oni(enso: pd.DataFrame, forecast_series: list[dict]) -> pd.DataFrame:
    """Quarterly ONI (with last quarter's) from observed months, then forecast months after them.

    Each month uses the observed ONI if it exists, otherwise the forecast. A quarter needs
    all 3 months.
    """
    observed = enso[["date", "oni"]].dropna()
    forecast = pd.DataFrame({
        "date": pd.to_datetime([row["month"] + "-01" for row in forecast_series]),
        "oni": [row["oni"] for row in forecast_series],
    })
    forecast = forecast[forecast["date"] > observed["date"].max()]  # observed months win
    monthly = pd.concat([observed, forecast], ignore_index=True)
    return add_previous_quarter(quarterly_oni(monthly), "oni", keys=[])


def forecast_quarters(enso: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    """The quarters after the last observed month: the ones only the forecast covers."""
    last = enso[["date", "oni"]].dropna()["date"].max()
    later = (oni["year"] > last.year) | ((oni["year"] == last.year) & (oni["quarter"] > last.quarter))
    quarters = oni[later].reset_index(drop=True)
    if quarters.empty or quarters[["oni", "oni_prev"]].isna().any().any():
        # XGBoost would quietly accept a missing ONI and predict nonsense.
        raise ValueError(f"Forecast quarters need ONI for this and last quarter:\n{quarters}")
    return quarters


def predicted_rain(quarters: pd.DataFrame, pcodes: list[str], rain_model) -> pd.DataFrame:
    """Predicted rainfall % for every province and forecast quarter."""
    rows = quarters[["year", "quarter", "oni", "oni_prev"]].merge(pd.DataFrame({"pcode": pcodes}), how="cross")
    # The model was trained with an int quarter and str pcode; other types are silently ignored.
    rows = rows.astype({"quarter": int, "pcode": str, "oni": float, "oni_prev": float})
    return rows.assign(rain_pct=rain_model.predict(rows))


def _shapes(lookup: pd.DataFrame, rain_by_pcode: pd.DataFrame) -> list[dict]:
    """One entry per map shape. Merged shapes share their province's rainfall."""
    shapes = lookup[["map_psgc", "crop_name", "rain_pcode"]].merge(
        rain_by_pcode, left_on="rain_pcode", right_on="pcode", how="left", validate="many_to_one")
    result = []
    for row in shapes.itertuples():
        rain_pct = None if pd.isna(row.rain_pct) else round(float(row.rain_pct), 1)
        result.append({
            "map_psgc": row.map_psgc,
            "province": None if pd.isna(row.crop_name) else row.crop_name,
            "rain_pct": rain_pct,
            "colour": dryness_colour(rain_pct),
        })
    return result


def _observed_view(rain: pd.DataFrame, lookup: pd.DataFrame, year: int | None, quarter: int) -> dict:
    rows = rain[(rain["year"] == year) & (rain["quarter"] == quarter)]
    return {"year": year, "shapes": _shapes(lookup, rows[["pcode", RAIN_TARGET]].rename(
        columns={RAIN_TARGET: "rain_pct"}))}


def latest_neutral_year(rain: pd.DataFrame, phases: pd.DataFrame, quarter: int) -> int | None:
    """The latest year whose `quarter` was neutral and has rainfall data."""
    with_rain = rain[["year", "quarter"]].drop_duplicates()
    neutral = phases[(phases["phase"] == "Neutral") & (phases["quarter"] == quarter)]
    candidates = neutral.merge(with_rain, on=["year", "quarter"])
    return None if candidates.empty else int(candidates["year"].max())


def map_views(enso: pd.DataFrame, forecast_series: list[dict], rain: pd.DataFrame,
              lookup: pd.DataFrame, rain_model) -> list[dict]:
    """All views for every forecast quarter, as plain dicts ready for JSON."""
    quarters = forecast_quarters(enso, combined_oni(enso, forecast_series))
    predicted = predicted_rain(quarters, sorted(rain["pcode"].unique()), rain_model)
    phases = quarter_phase(enso)

    output = []
    for q in quarters.itertuples():
        this_quarter = predicted[(predicted["year"] == q.year) & (predicted["quarter"] == q.quarter)]
        views = {
            "prediction": {"year": int(q.year), "shapes": _shapes(lookup, this_quarter[["pcode", "rain_pct"]])},
            "normal": _observed_view(rain, lookup, latest_neutral_year(rain, phases, q.quarter), q.quarter),
        }
        for name, years in PAST_EVENTS.items():
            views[name] = _observed_view(rain, lookup, years.get(q.quarter), q.quarter)
        output.append({
            "quarter": f"{q.year} Q{q.quarter}",
            "oni": round(float(q.oni), 2),
            "oni_prev": round(float(q.oni_prev), 2),
            "views": views,
        })
    return output


def load_map_views() -> list[dict]:
    """Map views from the saved models and the processed data."""
    enso = load_enso_monthly()
    forecast = forecast_from_bundle(layer1_train.load_model(), enso)
    rain_model = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.RAIN_MODEL_FILE)["model"]
    return map_views(enso, forecast["forecast_series"], load_rainfall(), load_lookup(), rain_model)


def main() -> None:
    for quarter in load_map_views():
        print(f"\n{quarter['quarter']}: ONI {quarter['oni']}, last quarter {quarter['oni_prev']}")
        for name, view in quarter["views"].items():
            counts = pd.Series([shape["colour"] for shape in view["shapes"]]).value_counts()
            text = ", ".join(f"{colour} {counts.get(colour, 0)}" for colour in ["green", "yellow", "red", "grey"])
            print(f"  {name:16s} year {view['year']}: {text}")


if __name__ == "__main__":
    main()
