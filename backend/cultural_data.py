from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CULTURAL_DATA_PATH = Path(
    os.getenv("CULTURAL_DATA_PATH", ROOT / "data" / "cultural_places.json")
)
_default_boundary = ROOT / "data" / "macau_boundary.geojson"
MACAU_BOUNDARY_PATH = os.getenv(
    "MACAU_BOUNDARY_PATH",
    str(_default_boundary) if _default_boundary.exists() else "",
)

# The export does not include an administrative boundary. This conservative
# outline is only a fallback; set MACAU_BOUNDARY_PATH to an official GeoJSON
# boundary for production use.
_MACAU_FALLBACK_POLYGONS = [
    [
        (113.525, 22.105),
        (113.575, 22.105),
        (113.575, 22.145),
        (113.555, 22.16),
        (113.535, 22.155),
        (113.525, 22.135),
    ],
    [
        (113.545, 22.135),
        (113.585, 22.135),
        (113.595, 22.175),
        (113.565, 22.19),
        (113.545, 22.175),
    ],
    [
        (113.535, 22.175),
        (113.575, 22.175),
        (113.575, 22.22),
        (113.535, 22.22),
    ],
]


def _point_in_polygon(lon: float, lat: float, polygon: list[tuple[float, float]]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        current_lon, current_lat = current
        previous_lon, previous_lat = previous
        crosses = (current_lat > lat) != (previous_lat > lat)
        if crosses:
            intersection_lon = (
                (previous_lon - current_lon) * (lat - current_lat)
                / (previous_lat - current_lat)
                + current_lon
            )
            if lon < intersection_lon:
                inside = not inside
        previous = current
    return inside


def _is_within_macau(lon: float, lat: float) -> bool:
    polygons = _boundary_polygons()
    return any(_point_in_polygon(lon, lat, polygon) for polygon in polygons)


@lru_cache(maxsize=1)
def _boundary_polygons() -> list[list[tuple[float, float]]]:
    if MACAU_BOUNDARY_PATH:
        path = Path(MACAU_BOUNDARY_PATH)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            geometries = []
            if payload.get("type") == "FeatureCollection":
                geometries = [feature["geometry"] for feature in payload.get("features", [])]
            elif payload.get("type") == "Feature":
                geometries = [payload.get("geometry")]
            else:
                geometries = [payload]
            polygons = []
            for geometry in geometries:
                if not geometry:
                    continue
                if geometry.get("type") == "Polygon":
                    polygons.extend(geometry.get("coordinates", [])[:1])
                elif geometry.get("type") == "MultiPolygon":
                    polygons.extend(
                        polygon[0] for polygon in geometry.get("coordinates", []) if polygon
                    )
            if polygons:
                return [[(float(point[0]), float(point[1])) for point in polygon] for polygon in polygons]
    return _MACAU_FALLBACK_POLYGONS


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_cultural_places() -> list[dict[str, Any]]:
    if not CULTURAL_DATA_PATH.exists():
        raise FileNotFoundError(f"Cultural places data was not found: {CULTURAL_DATA_PATH}")
    payload = json.loads(CULTURAL_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Cultural places data must be a JSON list")

    places: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        place = dict(item)
        place["area_status"] = (
            "macau" if _is_within_macau(float(longitude), float(latitude)) else "nearby"
        )
        places.append(place)
    return places
