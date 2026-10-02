from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

import httpx

ACTUAL_WEATHER_URL = "https://xml.smg.gov.mo/p_actual_brief.xml"
FORECAST_WEATHER_URL = "https://xml.smg.gov.mo/p_forecast.xml"
RAIN_STATUS_CODES = {str(code) for code in range(10, 21)} | {"24", "25", "28", "29", "30"}
RAIN_TERMS = (
    "雨", "驟雨", "雷雨", "大雨", "毛毛雨", "rain", "shower", "drizzle",
    "thunderstorm", "thundershower", "aguaceiro", "chuva",
)


@dataclass(frozen=True)
class WeatherSummary:
    available: bool
    raining: bool
    rain_forecast: bool
    condition: str | None = None
    forecast: str | None = None
    source: str = ACTUAL_WEATHER_URL
    recommendation: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _elements(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == name]


def _text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _has_rain(text: str) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in RAIN_TERMS)


def _status_is_rain(status: str) -> bool:
    normalized = status.strip().casefold()
    return normalized in RAIN_STATUS_CODES or normalized.lstrip("a") in RAIN_STATUS_CODES


def parse_weather_xml(actual_xml: str, forecast_xml: str | None = None) -> WeatherSummary:
    """Parse SMG XML defensively; malformed or empty feeds become unavailable."""
    try:
        actual_root = ET.fromstring(actual_xml)
    except (ET.ParseError, TypeError, ValueError):
        return WeatherSummary(available=False, raining=False, rain_forecast=False, error="invalid XML")
    try:
        forecast_root = ET.fromstring(forecast_xml) if forecast_xml else None
    except (ET.ParseError, TypeError, ValueError):
        forecast_root = None

    statuses = [_text(element) for element in _elements(actual_root, "WeatherStatus")]
    icons = [_text(element) for element in _elements(actual_root, "IconName")]
    descriptions = [
        _text(element)
        for element in _elements(actual_root, "WeatherDescription")
        + _elements(actual_root, "WeatherStatusDescription")
    ]
    actual_text = " ".join(statuses + icons + descriptions)
    forecast_descriptions = [_text(element) for element in _elements(forecast_root, "WeatherDescription")] if forecast_root is not None else []
    forecast_text = " ".join(forecast_descriptions)
    raining = any(_status_is_rain(status) for status in statuses) or _has_rain(actual_text)
    rain_forecast = _has_rain(forecast_text) or (
        forecast_root is not None and any(_status_is_rain(_text(element)) for element in _elements(forecast_root, "WeatherStatus"))
    )

    condition = descriptions[0] if descriptions else (statuses[0] if statuses else None)
    forecast = forecast_descriptions[0] if forecast_descriptions else None
    recommendation = (
        "正在下雨或預測有雨，請勿步行，建議改乘公車。"
        if raining or rain_forecast
        else None
    )
    return WeatherSummary(
        available=True,
        raining=raining,
        rain_forecast=rain_forecast,
        condition=condition,
        forecast=forecast,
        recommendation=recommendation,
    )


async def fetch_weather(
    fetcher: Callable[[str], Awaitable[str]] | None = None,
) -> WeatherSummary:
    """Fetch SMG actual and forecast feeds without allowing network errors to break routes."""
    if fetcher is not None:
        try:
            actual_xml, forecast_xml = await asyncio.gather(
                fetcher(ACTUAL_WEATHER_URL), fetcher(FORECAST_WEATHER_URL), return_exceptions=True
            )
        except Exception as exc:  # pragma: no cover - defensive around custom fetchers
            return WeatherSummary(False, False, False, error=str(exc))
    else:
        async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
            async def get(url: str) -> str:
                response = await client.get(url)
                response.raise_for_status()
                return response.text

            actual_xml, forecast_xml = await asyncio.gather(
                get(ACTUAL_WEATHER_URL), get(FORECAST_WEATHER_URL), return_exceptions=True
            )

    actual = actual_xml if isinstance(actual_xml, str) else None
    forecast = forecast_xml if isinstance(forecast_xml, str) else None
    if actual is None and forecast is None:
        return WeatherSummary(False, False, False, error="SMG feed unavailable")
    if actual is None:
        return WeatherSummary(False, False, False, forecast=forecast, error="current SMG feed unavailable")
    summary = parse_weather_xml(actual, forecast)
    if forecast_xml is not None and not isinstance(forecast_xml, str):
        return WeatherSummary(**{**summary.as_dict(), "error": "forecast SMG feed unavailable"})
    return summary
