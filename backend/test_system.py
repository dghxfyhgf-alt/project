from fastapi.testclient import TestClient
import networkx as nx
import numpy as np
import rasterio
from rasterio.transform import from_origin
from typing import Any
from unittest.mock import AsyncMock, patch

from .graph_builder import build_fallback_graph
from . import main as main_module
from .main import app, nearest_edge
from .bus_data import DsatBusClient
from .router import shortest_route
from .terrain import enrich_graph_with_dem
from .tour import LlmTourSelection


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


def test_local_bus_snapshot_endpoints() -> None:
    client = TestClient(app)
    routes = client.get("/bus/routes")
    stops = client.get("/bus/stops")
    assert routes.status_code == 200
    assert routes.json()["source"] == "local_snapshot"
    assert routes.json()["route_count"] == 117
    assert stops.status_code == 200
    assert stops.json()["source"] == "local_snapshot"
    assert stops.json()["stop_count"] == 286


def test_cultural_places_endpoint_has_map_details_and_area_status() -> None:
    response = TestClient(app).get("/cultural-places")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 341
    assert payload["boundary_mode"] == "official_file"
    assert {"macau", "nearby"} >= {place["area_status"] for place in payload["places"]}
    assert any(place["name_en"] for place in payload["places"])
    assert any(place["area_status"] == "nearby" for place in payload["places"])


def test_cultural_places_area_filter() -> None:
    response = TestClient(app).get("/cultural-places?area=nearby")
    assert response.status_code == 200
    assert all(place["area_status"] == "nearby" for place in response.json()["places"])


def test_tour_planner_requests_start_before_selecting_stops() -> None:
    response = TestClient(app).post(
        "/ai/plan_tour",
        json={"message": "我想看历史建筑和美食，下午有六小时"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["needs_clarification"] is True
    assert payload["stops"] == []


def test_tour_planner_returns_stops_and_legs() -> None:
    response = TestClient(app).post(
        "/ai/plan_tour",
        json={
            "message": "我想看历史建筑和美食，下午有六小时",
            "start_lat": 22.193,
            "start_lon": 113.539,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "plan_tour"
    assert len(payload["stops"]) > 0
    assert len(payload["legs"]) == len(payload["stops"])
    assert payload["needs_confirmation"] is True


def test_tour_planner_uses_validated_llm_selection() -> None:
    selection = LlmTourSelection(
        purpose="历史建筑深度游",
        categories=["history"],
        stop_ids=["ruins_of_st_paul", "monte_fort"],
        stay_minutes={"ruins_of_st_paul": 35},
        reasons={"ruins_of_st_paul": "模型根据历史主题选择"},
    )
    with patch.object(main_module, "llm_enabled", return_value=True), patch.object(
        main_module, "select_tour", new=AsyncMock(return_value=selection)
    ):
        response = TestClient(app).post(
            "/ai/plan_tour",
            json={"message": "我想深入了解澳门历史", "start_lat": 22.193, "start_lon": 113.539},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "llm"
    assert [stop["id"] for stop in payload["stops"]] == ["ruins_of_st_paul", "monte_fort"]
    assert payload["stops"][0]["stay_minutes"] == 35


def test_tour_route_validates_each_confirmed_leg() -> None:
    response = TestClient(app).post(
        "/tour/route",
        json={
            "stops": [
                {"id": "a", "name": "起点", "latitude": 22.193, "longitude": 113.539, "category": "history", "stay_minutes": 10, "reason": "test"},
                {"id": "b", "name": "终点", "latitude": 22.196, "longitude": 113.541, "category": "history", "stay_minutes": 10, "reason": "test"},
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["coordinates"]) >= 2
    assert payload["legs"][0]["route_available"] is True


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
