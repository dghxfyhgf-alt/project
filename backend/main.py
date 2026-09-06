from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .graph_builder import load_graph
from .bus_data import DsatBusClient
from .router import haversine_m, shortest_route
from .terrain import enrich_graph_with_dem, validate_dem

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = Path(os.getenv("GRAPH_PATH", ROOT / "data" / "macau_network.graphml"))
_default_pbf = ROOT / "data" / "macau.osm.pbf"
_downloads_pbf = Path.home() / "Downloads" / "macau-260904.osm.pbf"
PBF_PATH = Path(os.getenv("OSM_PBF_PATH", _default_pbf if _default_pbf.exists() else _downloads_pbf))
DEM_PATH = Path(os.getenv("DEM_PATH", ROOT / "data" / "dem.tif"))
app = FastAPI(title="Macau Adaptive Navigation API", version="2.0.0")
graph: nx.MultiDiGraph = load_graph(GRAPH_PATH, PBF_PATH)
dem_metadata = validate_dem(DEM_PATH)
dem_loaded = enrich_graph_with_dem(graph, DEM_PATH)


class RouteRequest(BaseModel):
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    end_lat: float = Field(..., ge=-90, le=90)
    end_lon: float = Field(..., ge=-180, le=180)
    weight: str = "length"
    avoid_stairs: bool = False
    max_slope: float | None = Field(None, ge=0, le=100)
    max_walk_km: float | None = Field(None, ge=0)
    prefer_bus: bool = False
    wheelchair: bool = False
    preferences: dict[str, Any] = Field(default_factory=dict)
    profile: str = Field("normal", pattern="^(normal|avoid_stairs|luggage|stroller|wheelchair)$")


class IntentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class UpdateRequest(RouteRequest):
    current_lat: float | None = Field(None, ge=-90, le=90)
    current_lon: float | None = Field(None, ge=-180, le=180)
    weather_alert: str | None = None


def nearest_node(lat: float, lon: float) -> Any:
    return min(graph.nodes, key=lambda node: haversine_m((lat, lon), (float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"]))))


def _project_to_segment(
    lat: float,
    lon: float,
    first: tuple[float, float],
    second: tuple[float, float],
) -> tuple[float, float, float]:
    scale = 111_320.0
    mid_lat = (first[0] + second[0]) / 2
    cos_lat = max(0.01, __import__("math").cos(__import__("math").radians(mid_lat)))
    px, py = lon * scale * cos_lat, lat * scale
    ax, ay = first[1] * scale * cos_lat, first[0] * scale
    bx, by = second[1] * scale * cos_lat, second[0] * scale
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    factor = 0.0 if denominator == 0 else ((px - ax) * dx + (py - ay) * dy) / denominator
    factor = max(0.0, min(1.0, factor))
    projected = (ay + factor * dy) / scale, (ax + factor * dx) / (scale * cos_lat)
    return projected[0], projected[1], haversine_m((lat, lon), projected)


def nearest_edge(lat: float, lon: float) -> tuple[Any, Any, float, float, float]:
    """Return the nearest directed edge and its projected map position."""
    nearest = None
    for start, end, key, data in graph.edges(keys=True, data=True):
        first = (float(graph.nodes[start]["y"]), float(graph.nodes[start]["x"]))
        second = (float(graph.nodes[end]["y"]), float(graph.nodes[end]["x"]))
        projected_lat, projected_lon, distance = _project_to_segment(lat, lon, first, second)
        if nearest is None or distance < nearest[2]:
            nearest = (start, end, distance, projected_lat, projected_lon)
    if nearest is None:
        raise HTTPException(status_code=503, detail="OSM 步行路网没有可用道路边。")
    return nearest


def route_graph_for_points(request: RouteRequest) -> tuple[nx.MultiDiGraph, Any, Any]:
    """Add projected virtual endpoints without changing the loaded base graph."""
    routed_graph = graph.copy()
    start_edge = nearest_edge(request.start_lat, request.start_lon)
    end_edge = nearest_edge(request.end_lat, request.end_lon)
    start_node, end_node = "__route_start__", "__route_end__"
    routed_graph.add_node(start_node, y=request.start_lat, x=request.start_lon)
    routed_graph.add_node(end_node, y=request.end_lat, x=request.end_lon)

    for virtual, edge_info, lat, lon in (
        (start_node, start_edge, request.start_lat, request.start_lon),
        (end_node, end_edge, request.end_lat, request.end_lon),
    ):
        left, right, _, projected_lat, projected_lon = edge_info
        projected_distance = haversine_m((lat, lon), (projected_lat, projected_lon))
        left_distance = haversine_m(
            (projected_lat, projected_lon),
            (float(graph.nodes[left]["y"]), float(graph.nodes[left]["x"])),
        )
        right_distance = haversine_m(
            (projected_lat, projected_lon),
            (float(graph.nodes[right]["y"]), float(graph.nodes[right]["x"])),
        )
        base_data = graph.get_edge_data(left, right) or {}
        edge_data = min(base_data.values(), key=lambda item: float(item.get("length", 1)), default={})
        for target, distance in ((left, left_distance), (right, right_distance)):
            attrs = dict(edge_data)
            attrs["length"] = distance + projected_distance
            routed_graph.add_edge(virtual, target, **attrs)
            routed_graph.add_edge(target, virtual, **attrs)
    return routed_graph, start_node, end_node


def geojson_route(request: RouteRequest) -> dict[str, Any]:
    routed_graph, origin, destination = route_graph_for_points(request)
    requested_distance = haversine_m(
        (request.start_lat, request.start_lon),
        (request.end_lat, request.end_lon),
    )
    preferences = request.preferences | {
        "avoid_stairs": request.avoid_stairs,
        "max_slope": request.max_slope,
        "max_walk_km": request.max_walk_km,
        "prefer_bus": request.prefer_bus,
        "wheelchair": request.wheelchair,
        "profile": request.profile,
    }
    if origin == destination:
        if requested_distance <= 30:
            coordinates = [
                [request.start_lon, request.start_lat],
                [request.end_lon, request.end_lat],
            ]
            properties = {
                "total_distance": requested_distance,
                "total_time": requested_distance / (5 / 3.6),
                "walk_distance": requested_distance,
                "bus_distance": 0,
                "num_transfers": 0,
                "weather_alert": None,
                "weight": request.weight,
                "node_count": 2,
                "terrain_source": "copernicus_dem" if dem_loaded else "unavailable",
                "profile": request.profile,
            }
            return {
                "type": "FeatureCollection",
                "properties": properties,
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": properties,
                }],
            }
        origin_candidates = list(routed_graph.predecessors(origin)) + list(routed_graph.successors(origin))
        origin_candidates = list(dict.fromkeys(origin_candidates))
        origin_candidates.sort(
            key=lambda node: haversine_m(
                (request.start_lat, request.start_lon),
                (float(routed_graph.nodes[node]["y"]), float(routed_graph.nodes[node]["x"])),
            )
        )
        destination_candidates = list(routed_graph.predecessors(destination)) + list(routed_graph.successors(destination))
        destination_candidates = list(dict.fromkeys(destination_candidates))
        destination_candidates.sort(
            key=lambda node: haversine_m(
                (request.end_lat, request.end_lon),
                (float(routed_graph.nodes[node]["y"]), float(routed_graph.nodes[node]["x"])),
            )
        )
        replacement = None
        for candidate_origin in origin_candidates[:8]:
            for candidate_destination in destination_candidates[:8]:
                if candidate_origin == candidate_destination:
                    continue
                try:
                    candidate_result = shortest_route(
                        routed_graph,
                        candidate_origin,
                        candidate_destination,
                        preferences,
                    )
                except nx.NetworkXNoPath:
                    continue
                if replacement is None or candidate_result.distance < replacement[2].distance:
                    replacement = (candidate_origin, candidate_destination, candidate_result)
        if replacement is None:
            detail = (
                "目前使用簡化測試路網，無法分辨這兩個不同位置；請先下載澳門 OSM walking network。"
                if routed_graph.graph.get("is_fallback", False)
                else "起點和終點落在同一路網節點附近，且附近沒有可行替代路徑；請重新選擇道路上的位置。"
            )
            raise HTTPException(status_code=503 if routed_graph.graph.get("is_fallback", False) else 422, detail=detail)
        origin, destination, result = replacement
    else:
        result = None
    if result is None:
        result = shortest_route(routed_graph, origin, destination, preferences)
    if request.max_walk_km is not None and result.distance > request.max_walk_km * 1000 and not request.prefer_bus:
        raise HTTPException(status_code=422, detail="路線超過最大步行距離")
    coordinates = [[float(routed_graph.nodes[node]["x"]), float(routed_graph.nodes[node]["y"])] for node in result.nodes]
    if coordinates[0] != [request.start_lon, request.start_lat]:
        coordinates.insert(0, [request.start_lon, request.start_lat])
    if coordinates[-1] != [request.end_lon, request.end_lat]:
        coordinates.append([request.end_lon, request.end_lat])
    properties = {
        "total_distance": result.distance,
        "total_time": result.duration,
        "walk_distance": result.distance if not request.prefer_bus else 0,
        "bus_distance": result.distance if request.prefer_bus else 0,
        "num_transfers": 0,
        "weather_alert": None,
        "weight": request.weight,
        "node_count": len(result.nodes),
        "terrain_source": "copernicus_dem" if dem_loaded else "unavailable",
        "profile": request.profile,
    }
    return {
        "type": "FeatureCollection",
        "properties": properties,
        "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": coordinates}, "properties": properties}],
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "graph_loaded": graph is not None,
        "node_count": graph.number_of_nodes(),
        "fallback_graph": graph.graph.get("is_fallback", False),
        "component_count": graph.graph.get("component_count", 1),
        "largest_component_nodes": graph.graph.get("largest_component_nodes", graph.number_of_nodes()),
        "graph_path": str(GRAPH_PATH),
        "osm_pbf_path": str(PBF_PATH),
        "dem_loaded": dem_loaded,
        "dem_path": str(DEM_PATH),
        "dem_metadata": dem_metadata,
    }


@app.post("/route/plan")
async def plan_route(request: RouteRequest) -> dict[str, Any]:
    try:
        geojson = geojson_route(request)
    except nx.NetworkXNoPath as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "起點和終點所在的步行道路網不連通，請選擇同一個可步行區域內的道路位置。"
                f"目前路網有 {graph.graph.get('component_count', 1)} 個連通區域。"
            ),
        ) from exc
    return {"success": True, "geojson": geojson}


@app.post("/route/update")
async def update_route(request: UpdateRequest) -> dict[str, Any]:
    result = geojson_route(request)
    result["properties"]["weather_alert"] = request.weather_alert
    return {"success": True, "rerouted": request.current_lat is not None, "geojson": result}


@app.post("/ai/parse_intent")
async def parse_intent(request: IntentRequest) -> dict[str, Any]:
    text = request.text.lower()
    tags = []
    for keyword, tag in (("地質", "geology"), ("歷史", "history"), ("美食", "food"), ("購物", "shopping"), ("自然", "nature")):
        if keyword in text:
            tags.append(tag)
    return {
        "tags": tags,
        "avoid_stairs": any(word in text for word in ("不要爬坡", "不想爬坡", "避開階梯", "無障礙")),
        "max_slope": 8 if "無障礙" in text else (10 if "坡" in text else None),
        "max_walk_km": float(next((value for value in __import__("re").findall(r"(\d+(?:\.\d+)?)\s*(?:公里|km)", text)), 0)) or None,
        "prefer_bus": any(word in text for word in ("公車", "巴士", "公交")),
        "wheelchair": "輪椅" in text or "无障碍" in text or "無障礙" in text,
        "poi_category": tags[0] if tags else None,
    }


@app.get("/geocode/search")
async def geocode_search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=10)) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get("https://nominatim.openstreetmap.org/search", params={"q": f"{q}, Macau", "format": "json", "limit": limit}, headers={"User-Agent": "MacauNavigation/2.0"})
    response.raise_for_status()
    return response.json()


@app.get("/geocode/reverse")
async def geocode_reverse(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get("https://nominatim.openstreetmap.org/reverse", params={"lat": lat, "lon": lon, "format": "json"}, headers={"User-Agent": "MacauNavigation/2.0"})
    response.raise_for_status()
    return response.json()


@app.get("/bus/routes")
async def bus_routes(language: str = Query("zh_tw", pattern="^(zh_tw|zh_cn|en|pt)$")) -> dict[str, Any]:
    """Expose public DSAT route metadata without pretending it is multimodal routing."""
    try:
        return DsatBusClient().route_list(language)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"DSAT 公交服务暂时不可用：{exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
