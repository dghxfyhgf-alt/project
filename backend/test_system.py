from fastapi.testclient import TestClient
import networkx as nx
import numpy as np
import rasterio
from rasterio.transform import from_origin
from typing import Any
from unittest.mock import patch

from .graph_builder import build_fallback_graph
from . import main as main_module
from .main import app, nearest_edge
from .bus_data import DsatBusClient
from .router import shortest_route
from .terrain import enrich_graph_with_dem


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["graph_loaded"] is True


def test_route_and_intent() -> None:
    client = TestClient(app)
    route = client.post("/route/plan", json={"start_lat": 22.1938271, "start_lon": 113.5399903, "end_lat": 22.196, "end_lon": 113.541})
    assert route.status_code == 200
    assert route.json()["success"] is True
    intent = client.post("/ai/parse_intent", json={"text": "坐公車，最多步行2公里"})
    assert intent.json()["prefer_bus"] is True
    assert intent.json()["max_walk_km"] == 2.0


def test_fallback_does_not_return_zero_for_distinct_points() -> None:
    with patch.object(main_module, "graph", build_fallback_graph()):
        response = TestClient(app).post(
            "/route/plan",
            json={
                "start_lat": 22.1938271,
                "start_lon": 113.5399903,
                "end_lat": 22.196,
                "end_lon": 113.541,
            },
        )
    assert response.status_code == 200
    payload = response.json()["geojson"]
    assert payload["properties"]["total_distance"] > 0
    assert len(payload["features"][0]["geometry"]["coordinates"]) >= 2


def test_nearest_edge_projection_returns_a_walkable_edge() -> None:
    with patch.object(main_module, "graph", build_fallback_graph()):
        left, right, distance, projected_lat, projected_lon = nearest_edge(22.192, 113.539)
        assert left != right
        assert distance >= 0
        assert 22.15 < projected_lat < 22.22
        assert 113.53 < projected_lon < 113.58


def test_dsat_bus_client_surfaces_session_requirement() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"header": "1200", "data": ""}

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
            return FakeResponse()

    with patch("backend.bus_data.httpx.Client", return_value=FakeClient()):
        try:
            DsatBusClient().route_list()
        except RuntimeError as exc:
            assert "token" in str(exc)
        else:
            raise AssertionError("DSAT session requirement was not reported")


def test_stairs_are_avoided_when_alternative_exists() -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("start", x=113.539, y=22.192)
    graph.add_node("stairs", x=113.540, y=22.192)
    graph.add_node("safe", x=113.539, y=22.193)
    graph.add_node("end", x=113.540, y=22.193)
    graph.add_edge("start", "stairs", length=1, highway="steps", is_stairs=True, slope=1)
    graph.add_edge("stairs", "end", length=1, highway="steps", is_stairs=True, slope=1)
    graph.add_edge("start", "safe", length=2, highway="residential", is_stairs=False, slope=1)
    graph.add_edge("safe", "end", length=2, highway="residential", is_stairs=False, slope=1)

    result = shortest_route(graph, "start", "end", {"profile": "wheelchair"})
    assert result.nodes == ["start", "safe", "end"]


def test_dem_enriches_edge_attributes(tmp_path) -> None:
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=113.5395, y=22.1925)
    graph.add_node("b", x=113.5405, y=22.1925)
    graph.add_edge("a", "b", length=100, highway="footway")
    dem_path = tmp_path / "dem.tif"
    transform = from_origin(113.539, 22.193, 0.001, 0.001)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dataset:
        dataset.write(np.array([[10, 10], [0, 0]], dtype="float32"), 1)

    assert enrich_graph_with_dem(graph, dem_path) is True
    edge = graph["a"]["b"][0]
    assert edge["terrain_source"] == "copernicus_dem"
    assert edge["terrain_quality"] == "measured"
    assert "max_slope_percent" in edge
