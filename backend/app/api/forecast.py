"""GET /api/forecast: the El Nino forecast from the saved model (layer1 spec, sections 2 and 12).

The route never trains and never runs the ERA5 loader: it only reads era5_monthly.csv.
Run `python -m app.layer1_forecast.train` from backend/ first.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.layer1_forecast import models, train
from app.layer1_forecast.features import add_era5_lags, build_features
from app.layer1_forecast.outputs import (
    build_outputs,
    climatology_rows,
    climatology_years,
    confidence_band,
)

router = APIRouter()


def forecast_from_bundle(bundle: dict, table: pd.DataFrame, era5: pd.DataFrame | None = None,
                         hindcast_year: int | None = None) -> dict:
    """Forecast leads 1 to 6 from the newest month in `table` (anchor B) and build the API fields.

    Uses the ERA5 version when the bundle has one and `era5` has every needed value at B and
    B-2. Otherwise (ERA5 missing, older than B, or a value empty) it falls back to the
    ONI-only version. `era5_used` says which ran; each version has its own confidence band.
    A hindcast passes a table cut at its anchor month and its year, so it uses that year's
    models and ERA5 normals from earlier years only.
    """
    latest = build_features(table).iloc[[-1]]  # newest row: its lags are known, its targets are not
    version, era5_used = bundle, False
    if bundle.get("uses_era5"):
        if era5 is not None:
            if hindcast_year is not None:
                era5 = train.hindcast_era5(era5, hindcast_year)
            with_era5 = add_era5_lags(latest, era5)  # empty when a needed ERA5 value is missing
            if len(with_era5):
                latest, era5_used = with_era5, True
        if not era5_used:
            version = bundle["oni_only"]

    if hindcast_year is None:
        models_by_lead, model_name = version["models"], version["model_name"]
    else:
        # An older model file has no hindcast models; that is a retrain case, not a server error.
        models_by_lead = version.get("hindcast_models", {}).get(hindcast_year)
        if models_by_lead is None:
            raise retrain_error(f"hindcast models for {hindcast_year} in {train.MODEL_FILE}")
        model_name = f"{version['model_name']} (hindcast)"

    anchor = latest["date"].iloc[0]
    features = latest[version["lag_columns"]]
    forecast = [models_by_lead[lead].predict(features)[0] for lead in bundle["leads"]]
    band = confidence_band(anchor, forecast, version["rmse_by_lead"])
    return {**build_outputs(table[["date", "oni"]], band, model_name), "era5_used": era5_used}


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


def hindcast(bundle: dict, table: pd.DataFrame, era5: pd.DataFrame | None, year: int) -> dict:
    """What the year's own model would have forecast at its anchor, next to the observed ONI."""
    cut = table[table["date"] <= train.hindcast_anchor(year)]
    result = forecast_from_bundle(bundle, cut, era5, hindcast_year=year)
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
        era5 = models.load_era5_monthly()  # None if not built; the forecast then uses ONI only
    except FileNotFoundError as missing:
        raise retrain_error(missing.filename) from missing

    if mode is None:
        return forecast_from_bundle(bundle, table, era5)
    if mode == "hindcast":
        result = hindcast(bundle, table, era5, year)
        note = (f"What the model would have forecast in {train.hindcast_anchor(year):%B %Y}, "
                "using only ONI up to then, next to what happened.")
    else:
        result = forecast_from_bundle(bundle, table, era5)
        series = result["forecast_series"]
        note = (f"Forecast for {series[0]['month']} to {series[-1]['month']}; "
                "months after that are not covered.")
    return {**result, "mode": mode, "target_year": year, "note": note}
