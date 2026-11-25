"""Province shapes for the front-end map (specs/frontend.md, section 4).

The 18 region files in data/raw/philippines/regions/medres/ hold the 88 map shapes (5.4 MB).
They are merged into one FeatureCollection with only the two properties the map uses, and the
coordinates are rounded to 3 decimals (about 110 m), which shrinks the output to about 2.3 MB.
"""

import errno
import json
from functools import cache
from pathlib import Path

from app.data.load_crops import RAW_DIR

SHAPES_DIR = RAW_DIR / "regions" / "medres"
DECIMALS = 3


def round_coordinates(coordinates):
    """Round every number in nested coordinate lists (Polygon and MultiPolygon nest differently)."""
    if isinstance(coordinates, (int, float)):
        return round(coordinates, DECIMALS)
    return [round_coordinates(item) for item in coordinates]


@cache  # built once per folder and kept in memory; a failed build raises and is not cached
def load_shapes(folder: Path) -> dict:
    files = sorted(folder.glob("*.json"))
    if not files:
        # filename is the folder, so the API's 503 says the data is missing (not "run train").
        raise FileNotFoundError(errno.ENOENT, "No shape files found", str(folder))
    features = []
    for path in files:
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            geometry = feature["geometry"]
            features.append({
                "type": "Feature",
                "properties": {
                    # The files store the code as a number, without the leading zero /api/map has.
                    "map_psgc": str(feature["properties"]["adm2_psgc"]).zfill(10),
                    "name": feature["properties"]["adm2_en"],
                },
                "geometry": {"type": geometry["type"],
                             "coordinates": round_coordinates(geometry["coordinates"])},
            })
    return {"type": "FeatureCollection", "features": features}
