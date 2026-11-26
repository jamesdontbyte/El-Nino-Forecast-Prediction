"""Layer 2 routes (specs/layer2-impact.md):

- GET /api/options: the provinces, crops and replay events (Layer 3) the front end can offer.
- GET /api/map: the dryness map views for every forecast quarter.
- GET /api/impact?province=...&crop=...: rainfall and yield change for one province and crop.
- GET /api/shapes: the 88 map shapes as one GeoJSON FeatureCollection, built once and kept in memory.
- GET /api/municipal_shapes: the 1,642 municipal shapes, built once and kept in memory.
- GET /api/municipal_map?quarter=...&view=...: rain % and colour per municipality for one forecast
  quarter and one past-data view (normal, el_nino_2015_16, el_nino_2023_24). Needs
  `python -m app.layer2.municipal_rain` to have been run.

The routes never train. Run `python -m app.layer1_forecast.train` and `python -m app.layer2.train`
from backend/ first. Files are read on every request, so retrained models are used without a restart.
"""

from fastapi import APIRouter, HTTPException

from app.layer2 import municipal_map, shapes
from app.layer2.features import load_lookup
from app.layer2.impact import CROP_TYPES, load_impact, province_names
from app.layer2.map_output import load_map_views
from app.simulation.simulate import REPLAY_EVENTS

router = APIRouter()

TRAIN_HINT = ("Run python -m app.layer1_forecast.train and python -m app.layer2.train "
              "from backend/ first.")


def missing_file(missing: FileNotFoundError) -> HTTPException:
    """503 naming the missing file. A missing model needs training; missing data needs the data files."""
    name = str(missing.filename)
    hint = TRAIN_HINT if name.endswith((".joblib", ".json")) else "The data file is missing (data/ is gitignored)."
    return HTTPException(status_code=503, detail=f"Missing {name}. {hint}")


@router.get("/api/options")
def get_options() -> dict:
    return {"provinces": province_names(load_lookup()), "crops": CROP_TYPES,
            "replay_events": [{"key": key, "label": label} for key, label in REPLAY_EVENTS.items()]}


@router.get("/api/map")
def get_map() -> list[dict]:
    try:
        return load_map_views()
    except FileNotFoundError as missing:
        raise missing_file(missing) from missing


@router.get("/api/shapes")
def get_shapes() -> dict:
    try:
        return shapes.load_shapes(shapes.SHAPES_DIR)  # read at call time, so a test can point it elsewhere
    except FileNotFoundError as missing:
        raise missing_file(missing) from missing


@router.get("/api/municipal_shapes")
def get_municipal_shapes() -> dict:
    try:
        return municipal_map.load_municipal_shapes(municipal_map.MUNICIPAL_DIR)
    except FileNotFoundError as missing:
        raise missing_file(missing) from missing


@router.get("/api/municipal_map")
def get_municipal_map(quarter: str, view: str) -> dict:
    try:
        return municipal_map.load_municipal_map(quarter, view)
    except municipal_map.BadMapRequest as bad_input:
        raise HTTPException(status_code=422, detail=str(bad_input)) from bad_input
    except FileNotFoundError as missing:
        if str(missing.filename).endswith(municipal_map.MUNICIPAL_RAIN_PATH.name):
            raise HTTPException(status_code=503, detail=(
                f"Missing {missing.filename}. Run python -m app.layer2.municipal_rain from backend/ first."
            )) from missing
        raise missing_file(missing) from missing


def check_province_and_crop(province: str, crop: str) -> None:
    """422 naming the bad value. Checked first, so a typo gives a clear error instead of an empty result."""
    if province not in province_names(load_lookup()):
        raise HTTPException(status_code=422, detail=f"Unknown province: {province!r}. See /api/options.")
    if crop not in CROP_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown crop: {crop!r}. Choose one of {CROP_TYPES}.")


@router.get("/api/impact")
def get_impact(province: str, crop: str) -> dict:
    check_province_and_crop(province, crop)
    try:
        return load_impact(province, crop)
    except FileNotFoundError as missing:
        raise missing_file(missing) from missing
