from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import networkx as nx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .graph_builder import load_graph
from .router import haversine_m, shortest_route

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = Path(os.getenv("GRAPH_PATH", ROOT / "data" / "macau_network.graphml"))
app = FastAPI(title="Macau Adaptive Navigation API", version="2.0.0")
graph: nx.MultiDiGraph = load_graph(GRAPH_PATH)


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


class IntentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class UpdateRequest(RouteRequest):
    current_lat: float | None = Field(None, ge=-90, le=90)
    current_lon: float | None = Field(None, ge=-180, le=180)
    weather_alert: str | None = None


def nearest_node(lat: float, lon: float) -> Any:
    return min(graph.nodes, key=lambda node: haversine_m((lat, lon), (float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"]))))


def geojson_route(request: RouteRequest) -> dict[str, Any]:
    origin = nearest_node(request.start_lat, request.start_lon)
    destination = nearest_node(request.end_lat, request.end_lon)
    preferences = request.preferences | {
        "avoid_stairs": request.avoid_stairs,
        "max_slope": request.max_slope,
        "max_walk_km": request.max_walk_km,
        "prefer_bus": request.prefer_bus,
        "wheelchair": request.wheelchair,
    }
    result = shortest_route(graph, origin, destination, preferences)
    if request.max_walk_km is not None and result.distance > request.max_walk_km * 1000 and not request.prefer_bus:
        raise HTTPException(status_code=422, detail="路線超過最大步行距離")
    coordinates = [[float(graph.nodes[node]["x"]), float(graph.nodes[node]["y"])] for node in result.nodes]
    properties = {
        "total_distance": result.distance,
        "total_time": result.duration,
        "walk_distance": result.distance if not request.prefer_bus else 0,
        "bus_distance": result.distance if request.prefer_bus else 0,
        "num_transfers": 0,
        "weather_alert": None,
        "weight": request.weight,
        "node_count": len(result.nodes),
    }
    return {
        "type": "FeatureCollection",
        "properties": properties,
        "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": coordinates}, "properties": properties}],
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "healthy", "graph_loaded": graph is not None, "node_count": graph.number_of_nodes()}


@app.post("/route/plan")
async def plan_route(request: RouteRequest) -> dict[str, Any]:
    try:
        geojson = geojson_route(request)
    except nx.NetworkXNoPath as exc:
        raise HTTPException(status_code=404, detail="找不到可行路徑") from exc
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
