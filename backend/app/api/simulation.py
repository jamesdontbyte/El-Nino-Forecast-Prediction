"""Layer 3 route (specs/layer3-simulation.md):

- GET /api/simulate?province=...&crop=...&irrigation=...&switching=...: the outcome without and
  with the chosen policies. pump_share, switch_share and irrigation_gain are optional assumptions.
  The optional event (a key from /api/options replay_events) replays a past El Nino instead of
  the live forecast.

The route never trains. Run `python -m app.layer1_forecast.train` and `python -m app.layer2.train`
from backend/ first. Files are read on every request, like the Layer 2 routes.
"""

from fastapi import APIRouter, HTTPException, Query

from app.api.layer2 import check_province_and_crop, missing_file
from app.simulation.simulate import (
    IRRIGATION_GAIN,
    PUMP_SHARE,
    REPLAY_EVENTS,
    SWITCH_SHARE,
    simulate,
)

router = APIRouter()


@router.get("/api/simulate")
def get_simulation(
    province: str,
    crop: str,
    irrigation: bool = False,
    switching: bool = False,
    # FastAPI returns 422 by itself when a value is outside these ranges.
    pump_share: float = Query(PUMP_SHARE, ge=0, le=1),
    switch_share: float = Query(SWITCH_SHARE, ge=0, le=1),
    irrigation_gain: float = Query(IRRIGATION_GAIN, ge=0, le=10),
    event: str | None = None,
) -> dict:
    check_province_and_crop(province, crop)
    if event is not None and event not in REPLAY_EVENTS:
        raise HTTPException(status_code=422, detail=f"Unknown event: {event!r}. See /api/options replay_events.")
    try:
        return simulate(province, crop, irrigation, switching, pump_share, switch_share, irrigation_gain, event)
    except FileNotFoundError as missing:
        raise missing_file(missing) from missing
