from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx


@dataclass
class RouteResult:
    nodes: list[Any]
    distance: float
    duration: float


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def shortest_route(
    graph: nx.MultiDiGraph,
    origin: Any,
    destination: Any,
    preferences: dict[str, Any] | None = None,
) -> RouteResult:
    preferences = preferences or {}

    def cost(_u: Any, _v: Any, data: dict[str, Any]) -> float:
        edge = min(data.values(), key=lambda item: float(item.get("length", 1))) if data else {}
        slope = float(edge.get("slope", 0))
        highway = str(edge.get("highway", ""))
        if preferences.get("avoid_stairs") and highway == "steps":
            return math.inf
        max_slope = preferences.get("max_slope")
        if max_slope is not None and slope > float(max_slope):
            return math.inf
        if preferences.get("wheelchair") and slope > 8:
            return math.inf
        length = float(edge.get("length", 1))
        return length * (1 + slope / 100)

    nodes = nx.shortest_path(graph, origin, destination, weight=cost)
    distance = 0.0
    for current, following in zip(nodes, nodes[1:]):
        edges = graph.get_edge_data(current, following) or {}
        edge = min(edges.values(), key=lambda item: float(item.get("length", 1)))
        distance += float(edge.get("length", 1))
    speed = 25 / 3.6 if preferences.get("prefer_bus") else 5 / 3.6
    return RouteResult(nodes=nodes, distance=distance, duration=distance / speed)
