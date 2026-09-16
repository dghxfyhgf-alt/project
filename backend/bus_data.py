from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


DSAT_BASE_URL = "https://bis.dsat.gov.mo:37812/macauweb"
ROUTE_LIST_PATH = "/ddbus/app/passenger/route"
STATION_LIST_PATH = "/ddbus/app/passenger/station"
LOCAL_BUS_DIR = Path(os.getenv("BUS_DATA_DIR", Path(__file__).resolve().parents[1] / "data" / "bus"))


class DsatBusClient:
    """Read public DSAT bus data without bypassing browser authentication."""

    def __init__(self, base_url: str = DSAT_BASE_URL, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = {"device": "web", **params}
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(f"{self.base_url}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("header") not in (None, "000"):
            raise RuntimeError(
                "DSAT 公交接口需要网页会话 token/HUID；未绕过访问控制。"
                f" DSAT status={payload.get('header')}"
            )
        if not isinstance(payload.get("data"), (dict, list)):
            raise RuntimeError("DSAT 公交接口没有返回可用数据。")
        return payload

    def route_list(self, language: str = "zh_tw") -> dict[str, Any]:
        return self._get(ROUTE_LIST_PATH, {"lang": language})

    def station_list(self, station_code: str, language: str = "zh_tw") -> dict[str, Any]:
        return self._get(STATION_LIST_PATH, {"stationCode": station_code, "lang": language})


def cache_public_bus_data(output: Path, language: str = "zh_tw") -> dict[str, Any]:
    """Fetch and cache route metadata; errors remain explicit for operators."""
    payload = DsatBusClient().route_list(language)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def local_bus_routes() -> list[dict[str, Any]]:
    """Read the operator-supplied, normalized bus snapshot without network access."""
    path = LOCAL_BUS_DIR / "routes.json"
    if not path.exists():
        raise FileNotFoundError(f"Local bus route data was not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Local bus route data must be a JSON list")
    return payload


def local_bus_stops() -> list[dict[str, Any]]:
    path = LOCAL_BUS_DIR / "stops.json"
    if not path.exists():
        raise FileNotFoundError(f"Local bus stop data was not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Local bus stop data must be a JSON list")
    return payload
