"""GET /api/forecast: the El Nino forecast from the saved model (layer1 spec, sections 2 and 12).

The route never trains. Run `python -m app.layer1_forecast.train` from backend/ first.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.layer1_forecast import models, train
from app.layer1_forecast.features import build_features
from app.layer1_forecast.outputs import (
    build_outputs,
    climatology_rows,
    climatology_years,
    confidence_band,
)

router = APIRouter()


def forecast_from_bundle(bundle: dict, table: pd.DataFrame, models_by_lead: dict | None = None,
                         model_name: str | None = None) -> dict:
    """Forecast leads 1 to 6 from the newest month in `table` (anchor B) and build the API fields.

    By default uses the saved live models. A hindcast passes a table cut at its anchor month
    and that year's models instead, so both share this one path.
    """
    models_by_lead = models_by_lead or bundle["models"]
    latest = build_features(table).iloc[[-1]]  # newest row: its lags are known, its targets are not
    anchor = latest["date"].iloc[0]
    features = latest[bundle["lag_columns"]]
    forecast = [models_by_lead[lead].predict(features)[0] for lead in bundle["leads"]]
    band = confidence_band(anchor, forecast, bundle["rmse_by_lead"])
    return build_outputs(table[["date", "oni"]], band, model_name or bundle["model_name"])


def forecast_mode(year: int, newest_month: pd.Timestamp) -> str:
    """Pick the mode for a target year from the newest ONI month B (layer1 spec, section 12)."""
    last_forecast_month = newest_month + pd.DateOffset(months=6)
    if year < newest_month.year:
        return "hindcast"
    if year <= last_forecast_month.year:
        return "forecast"
    return "climatology"


def retrain_error(missing: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"Missing {missing}. Run python -m app.layer1_forecast.train from backend/ first.",
    )


def hindcast(bundle: dict, table: pd.DataFrame, year: int) -> dict:
    """What the year's own model would have forecast at its anchor, next to the observed ONI."""
    # An older model file has no hindcast models; that is a retrain case, not a server error.
    models_by_lead = bundle.get("hindcast_models", {}).get(year)
    if models_by_lead is None:
        raise retrain_error(f"hindcast models for {year} in {train.MODEL_FILE}")
    cut = table[table["date"] <= train.hindcast_anchor(year)]
    result = forecast_from_bundle(bundle, cut, models_by_lead, f"{bundle['model_name']} (hindcast)")
    observed = dict(zip(table["date"].dt.strftime("%Y-%m"), table["oni"]))
    for month in result["forecast_series"]:
        oni = observed.get(month["month"])
        month["observed_oni"] = None if oni is None else round(oni, 2)
    return result


@router.get("/api/forecast")
def get_forecast(year: int | None = Query(None, ge=1960, le=2100)) -> dict:
    # Read on every request (both are small), so a retrained model is used without a restart.
    try:
        table = models.load_enso_monthly()
        newest_month = table["date"].max()
        mode = None if year is None else forecast_mode(year, newest_month)
        if mode == "climatology":
            first_year, last_year = climatology_years(table)
            return {
                "mode": mode, "target_year": year,
                "note": f"Average of {first_year} to {last_year}, not a forecast.",
                "model_used": "climatology (no model)", "climatology": climatology_rows(table),
            }
        bundle = train.load_model(train.SAVED_MODELS_DIR)
    except FileNotFoundError as missing:
        raise retrain_error(missing.filename) from missing

    if mode is None:
        return forecast_from_bundle(bundle, table)
    if mode == "hindcast":
        result = hindcast(bundle, table, year)
        note = (f"What the model would have forecast in {train.hindcast_anchor(year):%B %Y}, "
                "using only ONI up to then, next to what happened.")
    else:
        result = forecast_from_bundle(bundle, table)
        series = result["forecast_series"]
        note = (f"Forecast for {series[0]['month']} to {series[-1]['month']}; "
                "months after that are not covered.")
    return {**result, "mode": mode, "target_year": year, "note": note}
