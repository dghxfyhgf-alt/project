from .main import app
from .weather import fetch_weather, parse_weather_xml
from fastapi.testclient import TestClient


def test_parse_rain_and_forecast() -> None:
    actual = "<ActualWeatherBrief><Custom><WeatherStatus>12</WeatherStatus></Custom></ActualWeatherBrief>"
    forecast = "<ActualForecast><Custom><WeatherForecast><WeatherDescription>Occasional showers</WeatherDescription></WeatherForecast></Custom></ActualForecast>"
    result = parse_weather_xml(actual, forecast)
    assert result.available is True
    assert result.raining is True
    assert result.rain_forecast is True
    assert "公車" in result.recommendation


def test_parse_dry_feed() -> None:
    result = parse_weather_xml("<ActualWeatherBrief><Custom><WeatherStatus>a1</WeatherStatus></Custom></ActualWeatherBrief>")
    assert result.available is True
    assert result.raining is False
    assert result.recommendation is None


def test_parse_malformed_xml_is_safe() -> None:
    result = parse_weather_xml("<not valid")
    assert result.available is False
    assert result.raining is False


def test_malformed_forecast_does_not_discard_current_weather() -> None:
    result = parse_weather_xml(
        "<ActualWeatherBrief><Custom><WeatherStatus>a1</WeatherStatus></Custom></ActualWeatherBrief>",
        "<forecast",
    )
    assert result.available is True
    assert result.rain_forecast is False


def test_fetch_failure_is_safe() -> None:
    async def fail(_url: str) -> str:
        raise OSError("offline")

    result = __import__("asyncio").run(fetch_weather(fail))
    assert result.available is False
    assert "unavailable" in result.error


def test_weather_endpoint_and_route_recommend_bus(monkeypatch) -> None:
    async def rainy_weather():
        return parse_weather_xml("<ActualWeatherBrief><Custom><WeatherStatus>16</WeatherStatus></Custom></ActualWeatherBrief>")

    monkeypatch.setattr("backend.main.fetch_weather", rainy_weather)
    client = TestClient(app)
    weather = client.get("/weather/current")
    assert weather.json()["recommendation"]
    route = client.post("/route/plan", json={"start_lat": 22.192, "start_lon": 113.539, "end_lat": 22.188, "end_lon": 113.535})
    assert route.status_code == 200
    assert "公車" in route.json()["geojson"]["properties"]["weather_recommendation"]
