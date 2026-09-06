from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx

try:
    import rasterio
    from pyproj import Transformer
except ImportError:  # pragma: no cover - optional when DEM processing is unused
    rasterio = None
    Transformer = None

from .router import haversine_m


def _is_stairs(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return "steps" in {str(item).lower() for item in value}
    return str(value or "").lower() == "steps"


def _edge_points(graph: nx.MultiDiGraph, start: Any, end: Any, data: dict[str, Any]) -> list[tuple[float, float]]:
    geometry = data.get("geometry")
    if hasattr(geometry, "coords"):
        return [(float(lon), float(lat)) for lon, lat, *_ in geometry.coords]
    start_data, end_data = graph.nodes[start], graph.nodes[end]
    return [
        (float(start_data["x"]), float(start_data["y"])),
        (float(end_data["x"]), float(end_data["y"])),
    ]


def _sample_elevations(
    points: list[tuple[float, float]],
    dataset: Any,
    transformer: Any,
) -> list[float | None]:
    projected = [transformer.transform(lon, lat) for lon, lat in points]
    values = []
    for x, y in projected:
        row, column = dataset.index(x, y)
        if row < 0 or column < 0 or row >= dataset.height or column >= dataset.width:
            values.append(None)
            continue
        values.append(float(next(dataset.sample([(x, y)]))[0]))
    nodata = dataset.nodata
    return [
        None
        if value is None or (nodata is not None and value == nodata) or math.isnan(value)
        else value
        for value in values
    ]


def enrich_graph_with_dem(graph: nx.MultiDiGraph, dem_path: Path) -> bool:
    """Add terrain attributes to graph edges from a local GeoTIFF DEM.

    The source graph remains usable when no DEM is present. OSM's explicit
    ``highway=steps`` tag is always preserved independently of DEM coverage.
    """
    if rasterio is None or Transformer is None or not dem_path.exists():
        return False

    with rasterio.open(dem_path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"DEM has no CRS metadata: {dem_path}")
        transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        for start, end, _key, data in graph.edges(keys=True, data=True):
            points = _edge_points(graph, start, end, data)
            elevations = _sample_elevations(points, dataset, transformer)
            valid_pairs = [
                (point, value)
                for point, value in zip(points, elevations)
                if value is not None
            ]
            valid = [value for _point, value in valid_pairs]
            data["is_stairs"] = _is_stairs(data.get("highway")) or bool(data.get("is_stairs", False))
            data["terrain_source"] = "copernicus_dem"
            if len(valid) < 2:
                data["terrain_quality"] = "missing"
                continue

            grades = []
            for (point_a, first), (point_b, second) in zip(valid_pairs, valid_pairs[1:]):
                horizontal = haversine_m((point_a[1], point_a[0]), (point_b[1], point_b[0]))
                if horizontal > 0:
                    grades.append((second - first) / horizontal * 100)
            data["elevation_start_m"] = valid[0]
            data["elevation_end_m"] = valid[-1]
            data["elevation_gain_m"] = max(valid[-1] - valid[0], 0.0)
            data["elevation_loss_m"] = max(valid[0] - valid[-1], 0.0)
            data["average_slope_percent"] = sum(abs(value) for value in grades) / len(grades) if grades else 0.0
            data["max_slope_percent"] = max((abs(value) for value in grades), default=0.0)
            data["slope_direction"] = "uphill" if grades[-1] > 0 else "downhill" if grades[-1] < 0 else "flat"
            data["slope"] = data["max_slope_percent"]
            data["terrain_quality"] = "measured"
    return True


def validate_dem(dem_path: Path) -> dict[str, Any]:
    """Return safe-to-log metadata for a local DEM before processing it."""
    if rasterio is None:
        return {"valid": False, "reason": "rasterio_not_installed"}
    if not dem_path.exists():
        return {"valid": False, "reason": "file_not_found", "path": str(dem_path)}
    with rasterio.open(dem_path) as dataset:
        return {
            "valid": dataset.crs is not None and dataset.count >= 1,
            "path": str(dem_path),
            "crs": str(dataset.crs) if dataset.crs else None,
            "width": dataset.width,
            "height": dataset.height,
            "resolution": tuple(round(value, 3) for value in dataset.res),
            "nodata": dataset.nodata,
            "bounds": tuple(round(value, 6) for value in dataset.bounds),
        }
