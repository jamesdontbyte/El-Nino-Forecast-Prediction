"""GET /api/forecast: the El Nino forecast from the saved model (layer1 spec, section 2).

The route never trains. Run `python -m app.layer1_forecast.train` from backend/ first.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.layer1_forecast import models, train
from app.layer1_forecast.features import build_features
from app.layer1_forecast.outputs import build_outputs, confidence_band

router = APIRouter()


def forecast_from_bundle(bundle: dict, table: pd.DataFrame) -> dict:
    """Forecast leads 1 to 6 from the newest ONI month (anchor B) and build the API fields."""
    latest = build_features(table).iloc[[-1]]  # newest row: its lags are known, its targets are not
    anchor = latest["date"].iloc[0]
    features = latest[bundle["lag_columns"]]
    forecast = [bundle["models"][lead].predict(features)[0] for lead in bundle["leads"]]
    band = confidence_band(anchor, forecast, bundle["rmse_by_lead"])
    return build_outputs(table[["date", "oni"]], band, bundle["model_name"])


@router.get("/api/forecast")
def get_forecast() -> dict:
    # Read on every request (both are small), so a retrained model is used without a restart.
    try:
        bundle = train.load_model(train.SAVED_MODELS_DIR)
        table = models.load_enso_monthly()
    except FileNotFoundError as missing:
        raise HTTPException(
            status_code=503,
            detail=f"Missing {missing.filename}. Run python -m app.layer1_forecast.train from backend/ first.",
        ) from missing
    return forecast_from_bundle(bundle, table)
