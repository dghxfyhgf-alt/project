from fastapi.testclient import TestClient

from .main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["graph_loaded"] is True


def test_route_and_intent() -> None:
    client = TestClient(app)
    route = client.post("/route/plan", json={"start_lat": 22.218, "start_lon": 113.550, "end_lat": 22.155, "end_lon": 113.570})
    assert route.status_code == 200
    assert route.json()["success"] is True
    intent = client.post("/ai/parse_intent", json={"text": "坐公車，最多步行2公里"})
    assert intent.json()["prefer_bus"] is True
    assert intent.json()["max_walk_km"] == 2.0
