from __future__ import annotations

import os
import io
from pathlib import Path
from typing import Any

import httpx
import networkx as nx
import numpy as np
import rasterio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field

from .graph_builder import load_graph
from .bus_data import DsatBusClient, local_bus_routes, local_bus_stops
from .cultural_data import MACAU_BOUNDARY_PATH, load_cultural_places
from .llm import llm_enabled, select_tour
from .router import haversine_m, shortest_route
from .terrain import enrich_graph_with_dem, validate_dem
from .tour import (
    TourLeg,
    TourPlan,
    TourRequest,
    TourRouteRequest,
    TourRouteResponse,
    TourStop,
    candidate_pois,
    parse_tour_intent,
    POIS,
)

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
cultural_places = load_cultural_places()


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
        "cultural_places_loaded": len(cultural_places),
        "cultural_places_endpoint": True,
    }


@app.get("/terrain/overlay.png")
async def terrain_overlay() -> Response:
    """Render the local DEM as a transparent elevation overlay for Flutter."""
    if not dem_loaded or not DEM_PATH.exists():
        raise HTTPException(status_code=404, detail="DEM 地形图层尚未加载。")
    with rasterio.open(DEM_PATH) as dataset:
        values = dataset.read(1, masked=True).astype("float32")
        valid = values.compressed()
        if valid.size == 0:
            raise HTTPException(status_code=422, detail="DEM 没有有效高程值。")
        low, high = float(valid.min()), float(valid.max())
        normalized = np.ma.filled((values - low) / max(high - low, 1.0), 0.0)
        rgba = np.zeros((*normalized.shape, 4), dtype=np.uint8)
        rgba[..., 0] = (normalized * 255).astype(np.uint8)
        rgba[..., 1] = ((1.0 - normalized) * 180 + 40).astype(np.uint8)
        rgba[..., 2] = ((1.0 - normalized) * 100 + 80).astype(np.uint8)
        rgba[..., 3] = np.where(values.mask, 0, 105).astype(np.uint8)
        output = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(output, format="PNG", optimize=True)
    return Response(content=output.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


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
    """Return the local supplied snapshot, with DSAT live data as an explicit fallback."""
    try:
        routes = local_bus_routes()
        return {
            "source": "local_snapshot",
            "route_count": len(routes),
            "routes": routes,
            "warning": "公交快照由用户提供；不是实时车辆位置。",
        }
    except (FileNotFoundError, ValueError):
        pass
    try:
        return DsatBusClient().route_list(language)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"DSAT 公交服务暂时不可用：{exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/bus/stops")
async def bus_stops() -> dict[str, Any]:
    try:
        stops = local_bus_stops()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "source": "local_snapshot",
        "stop_count": len(stops),
        "stops": stops,
        "warning": "站点名称和编号来自用户提供的 Excel 快照。",
    }


@app.get("/cultural-places")
async def cultural_places_endpoint(
    area: str = Query("all", pattern="^(all|macau|nearby)$"),
    category: str | None = Query(None, max_length=50),
) -> dict[str, Any]:
    places = cultural_places
    if area != "all":
        places = [place for place in places if place["area_status"] == area]
    if category:
        places = [
            place
            for place in places
            if category in {
                place.get("tourism"),
                place.get("amenity"),
                place.get("historic"),
                place.get("heritage"),
            }
        ]
    return {
        "source": "HOT OSM cultural_places snapshot",
        "snapshot": "2026-08-07",
        "license": "ODbL",
        "count": len(places),
        "boundary_mode": "official_file" if MACAU_BOUNDARY_PATH else "fallback_approximation",
        "warning": None
        if MACAU_BOUNDARY_PATH
        else "请配置 MACAU_BOUNDARY_PATH 使用官方澳门行政边界；当前边界为保守近似范围。",
        "places": places,
    }


@app.post("/ai/plan_tour", response_model=TourPlan)
async def plan_tour(request: TourRequest) -> TourPlan:
    purpose, categories, parsed_minutes, parsed_max_stops = parse_tour_intent(request.message)
    available_minutes = request.available_minutes or parsed_minutes
    max_stops = min(request.max_stops, parsed_max_stops)
    if request.start_lat is None or request.start_lon is None:
        return TourPlan(
            intent="plan_tour",
            purpose=purpose,
            categories=categories,
            stops=[],
            legs=[],
            total_distance_m=0,
            total_duration_minutes=0,
            needs_clarification=True,
            clarification_question="请提供起点，或在地图上选择起点。",
        )

    warnings: list[str] = []
    source = "rules"
    if llm_enabled():
        try:
            selection = await select_tour(
                request.message,
                available_minutes,
                max_stops,
                request.prefer_bus,
                request.profile,
                POIS,
            )
            poi_by_id = {poi.id: poi for poi in POIS}
            selected_ids = list(dict.fromkeys(selection.stop_ids))[:max_stops]
            pois = [poi_by_id[stop_id] for stop_id in selected_ids]
            purpose = selection.purpose
            categories = selection.categories or categories
            stay_overrides = {
                stop_id: max(5, min(240, minutes))
                for stop_id, minutes in selection.stay_minutes.items()
                if stop_id in poi_by_id
            }
            reason_overrides = {
                stop_id: reason[:500]
                for stop_id, reason in selection.reasons.items()
                if stop_id in poi_by_id
            }
            source = "llm"
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            warnings.append(f"LLM 规划暂时不可用，已切换为本地规划：{exc}")
            pois = candidate_pois(categories, max_stops)
            stay_overrides = {}
            reason_overrides = {}
    else:
        pois = candidate_pois(categories, max_stops)
        stay_overrides = {}
        reason_overrides = {}
    stops = [
        TourStop(
            id=poi.id,
            name=poi.name,
            latitude=poi.latitude,
            longitude=poi.longitude,
            category=poi.category,
            stay_minutes=stay_overrides.get(poi.id, poi.stay_minutes),
            reason=reason_overrides.get(poi.id, poi.reason),
        )
        for poi in pois
    ]
    legs: list[TourLeg] = []
    total_distance = 0.0
    total_duration = 0.0
    current = (request.start_lat, request.start_lon)
    current_id = "start"
    for stop in stops:
        distance = haversine_m(current, (stop.latitude, stop.longitude))
        duration = distance / (25 / 3.6 if request.prefer_bus else 5 / 3.6) / 60
        legs.append(TourLeg(
            start_stop_id=current_id,
            end_stop_id=stop.id,
            distance_m=distance,
            duration_minutes=duration,
            mode="bus" if request.prefer_bus else "walk",
            route_available=True,
            warning="公交实时路线尚未接入；当前为公交偏好标记。" if request.prefer_bus else None,
        ))
        total_distance += distance
        total_duration += duration + stop.stay_minutes
        current = (stop.latitude, stop.longitude)
        current_id = stop.id

    if request.end_lat is not None and request.end_lon is not None:
        distance = haversine_m(current, (request.end_lat, request.end_lon))
        duration = distance / (25 / 3.6 if request.prefer_bus else 5 / 3.6) / 60
        legs.append(TourLeg(
            start_stop_id=current_id,
            end_stop_id="end",
            distance_m=distance,
            duration_minutes=duration,
            mode="bus" if request.prefer_bus else "walk",
            route_available=True,
            warning="公交实时路线尚未接入；当前为公交偏好标记。" if request.prefer_bus else None,
        ))
        total_distance += distance
        total_duration += duration
    if available_minutes is not None and total_duration > available_minutes:
        warnings.append(f"候选行程约需 {total_duration:.0f} 分钟，超过可用时间 {available_minutes} 分钟。")
    if request.max_walk_km is not None and total_distance > request.max_walk_km * 1000 and not request.prefer_bus:
        warnings.append("候选行程超过最大步行距离，确认前需要删减景点。")
    return TourPlan(
        intent="plan_tour",
        purpose=purpose,
        categories=categories,
        stops=stops,
        legs=legs,
        total_distance_m=total_distance,
        total_duration_minutes=total_duration,
        warnings=warnings,
        source=source,
    )


@app.post("/tour/route", response_model=TourRouteResponse)
async def route_tour(request: TourRouteRequest) -> TourRouteResponse:
    """Validate and join each confirmed tour leg using the OSM route engine."""
    coordinates: list[list[float]] = []
    legs: list[TourLeg] = []
    warnings: list[str] = []
    total_distance = 0.0
    total_duration = 0.0
    for index, (start, end) in enumerate(zip(request.stops, request.stops[1:])):
        try:
            geojson = geojson_route(RouteRequest(
                start_lat=start.latitude,
                start_lon=start.longitude,
                end_lat=end.latitude,
                end_lon=end.longitude,
                prefer_bus=request.prefer_bus,
                profile=request.profile,
                max_slope=request.max_slope,
            ))
        except (HTTPException, nx.NetworkXNoPath) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else "找不到可行步行路线"
            warnings.append(f"{start.name} → {end.name}：{detail}")
            legs.append(TourLeg(
                start_stop_id=start.id,
                end_stop_id=end.id,
                distance_m=0,
                duration_minutes=0,
                mode="bus" if request.prefer_bus else "walk",
                route_available=False,
                warning=str(detail),
            ))
            continue
        feature = geojson["features"][0]
        leg_coordinates = feature["geometry"]["coordinates"]
        if coordinates:
            leg_coordinates = leg_coordinates[1:]
        coordinates.extend(leg_coordinates)
        properties = geojson["properties"]
        distance = float(properties["total_distance"])
        duration = float(properties["total_time"]) / 60
        total_distance += distance
        total_duration += duration + end.stay_minutes
        legs.append(TourLeg(
            start_stop_id=start.id,
            end_stop_id=end.id,
            distance_m=distance,
            duration_minutes=duration,
            mode="bus" if request.prefer_bus else "walk",
            route_available=True,
            warning="公交实时路线尚未接入；当前路线为步行路网验证结果。" if request.prefer_bus else None,
        ))
    if not coordinates:
        raise HTTPException(status_code=404, detail="所有行程段都没有可行路线。")
    return TourRouteResponse(
        success=not warnings,
        stops=request.stops,
        legs=legs,
        coordinates=coordinates,
        total_distance_m=total_distance,
        total_duration_minutes=total_duration,
        warnings=warnings,
    )
