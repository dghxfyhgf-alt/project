from __future__ import annotations

from pathlib import Path
from math import cos, radians, sqrt
from typing import Any

import networkx as nx

try:
    import osmnx as ox
except ImportError:  # pragma: no cover - optional for offline fallback
    ox = None

try:
    import osmium
except ImportError:  # pragma: no cover - optional for offline fallback
    osmium = None


def build_fallback_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["is_fallback"] = True
    points = {
        "north": (22.218, 113.550),
        "center": (22.192, 113.539),
        "south": (22.155, 113.570),
        "west": (22.188, 113.535),
        "east": (22.188, 113.548),
    }
    for node, (lat, lon) in points.items():
        graph.add_node(node, y=lat, x=lon)
    links = [
        ("north", "center"), ("center", "south"), ("center", "west"),
        ("center", "east"), ("west", "south"), ("east", "south"),
    ]
    for left, right in links:
        a = points[left]
        b = points[right]
        length = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 * 111_000
        attributes = {
            "length": length,
            "slope": 2.0,
            "average_slope_percent": 2.0,
            "max_slope_percent": 2.0,
            "is_stairs": False,
            "highway": "residential",
        }
        graph.add_edge(left, right, **attributes)
        graph.add_edge(right, left, **attributes)
    return graph


def load_graph(path: Path, pbf_path: Path | None = None) -> nx.MultiDiGraph:
    cache_is_current = (
        path.exists()
        and (pbf_path is None or not pbf_path.exists() or path.stat().st_mtime >= pbf_path.stat().st_mtime)
    )
    if cache_is_current and ox is not None:
        graph = ox.load_graphml(path)
        graph.graph["is_fallback"] = False
        return normalize_osm_attributes(clean_graph_components(graph))
    if pbf_path is not None and pbf_path.exists():
        graph = load_pbf_graph(pbf_path)
        graph.graph["is_fallback"] = False
        if ox is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            ox.save_graphml(graph, filepath=path)
        return clean_graph_components(graph)
    return build_fallback_graph()


_WALKABLE_HIGHWAYS = {
    "footway", "path", "pedestrian", "steps", "track", "living_street",
    "residential", "service", "tertiary", "secondary", "primary",
    "unclassified", "cycleway",
}


def _edge_distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = first
    lat2, lon2 = second
    lat_scale = 111_320
    lon_scale = 111_320 * cos(radians((lat1 + lat2) / 2))
    return sqrt(((lat2 - lat1) * lat_scale) ** 2 + ((lon2 - lon1) * lon_scale) ** 2)


def load_pbf_graph(path: Path) -> nx.MultiDiGraph:
    """Build a walking graph from an OSM PBF file and cache it as GraphML."""
    if osmium is None:
        raise RuntimeError("The osmium package is required to read OSM PBF files")

    class PbfHandler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.nodes: dict[int, tuple[float, float]] = {}
            self.ways: list[tuple[list[int], dict[str, str]]] = []

        def node(self, node: Any) -> None:
            if node.location.valid():
                self.nodes[node.id] = (node.location.lat, node.location.lon)

        def way(self, way: Any) -> None:
            tags = {str(tag.k): str(tag.v) for tag in way.tags}
            highway = tags.get("highway", "").lower()
            if highway in _WALKABLE_HIGHWAYS and len(way.nodes) >= 2:
                self.ways.append(([node.ref for node in way.nodes], tags))

    handler = PbfHandler()
    handler.apply_file(str(path), locations=True)
    graph = nx.MultiDiGraph()
    for refs, tags in handler.ways:
        valid_refs = [ref for ref in refs if ref in handler.nodes]
        highway = tags.get("highway", "path")
        for ref in valid_refs:
            lat, lon = handler.nodes[ref]
            graph.add_node(str(ref), y=lat, x=lon)
        for start, end in zip(valid_refs, valid_refs[1:]):
            attributes = {
                "length": _edge_distance_m(handler.nodes[start], handler.nodes[end]),
                "highway": highway,
                "is_stairs": highway == "steps",
                "is_walkway": highway in {"footway", "path", "pedestrian", "steps", "track"},
            }
            if "incline" in tags:
                attributes["incline"] = tags["incline"]
            graph.add_edge(str(start), str(end), **attributes)
            if tags.get("oneway", "").lower() not in {"yes", "true", "1"}:
                graph.add_edge(str(end), str(start), **attributes)
    if graph.number_of_nodes() == 0:
        raise ValueError(f"No walkable roads found in OSM PBF: {path}")
    return normalize_osm_attributes(graph)


def clean_graph_components(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Keep the largest walkable component and expose connectivity metadata."""
    components = list(nx.weakly_connected_components(graph))
    graph.graph["component_count"] = len(components)
    if not components:
        raise ValueError("OSM graph contains no connected components")
    largest = max(components, key=len)
    if len(components) > 1:
        graph = graph.subgraph(largest).copy()
    graph.graph["largest_component_nodes"] = graph.number_of_nodes()
    return graph


def normalize_osm_attributes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Normalize OSM tags used by terrain and routing code."""
    for _start, _end, _key, data in graph.edges(keys=True, data=True):
        highway = data.get("highway", "")
        if isinstance(highway, (list, tuple)):
            highway_values = {str(value).lower() for value in highway}
        else:
            highway_values = {str(highway).lower()}
        data["is_stairs"] = "steps" in highway_values
        data["is_walkway"] = bool(highway_values & {"footway", "path", "pedestrian", "steps", "track"})
        if "incline" in data:
            try:
                incline = str(data["incline"]).strip().rstrip("%")
                data["incline_percent"] = float(incline)
            except (TypeError, ValueError):
                data["incline_percent"] = None
    return graph


def download_macau_network(output: Path) -> nx.MultiDiGraph:
    if ox is None:
        raise RuntimeError("OSMnx is required to download a real road network")
    output.parent.mkdir(parents=True, exist_ok=True)
    graph = ox.graph_from_place("Macau", network_type="walk")
    graph = normalize_osm_attributes(graph)
    ox.save_graphml(graph, filepath=output)
    return graph
