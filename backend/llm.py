from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .tour import LlmTourSelection, Poi

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


def llm_enabled() -> bool:
    return bool(LLM_API_KEY)


def _catalog(pois: tuple[Poi, ...]) -> list[dict[str, Any]]:
    return [
        {
            "id": poi.id,
            "name": poi.name,
            "latitude": poi.latitude,
            "longitude": poi.longitude,
            "category": poi.category,
            "default_stay_minutes": poi.stay_minutes,
        }
        for poi in pois
    ]


async def select_tour(
    message: str,
    available_minutes: int | None,
    max_stops: int,
    prefer_bus: bool,
    profile: str,
    pois: tuple[Poi, ...],
) -> LlmTourSelection:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not configured")

    system = (
        "You are a Macau tour planner. Select only stops from the supplied catalog. "
        "Never invent IDs, coordinates, opening hours, or transit availability. "
        "Return a JSON object with purpose, categories, stop_ids, stay_minutes, and reasons. "
        "Respect the requested number of stops "
        "and time budget as much as possible. The backend will validate every route."
    )
    user = json.dumps(
        {
            "request": message,
            "available_minutes": available_minutes,
            "max_stops": max_stops,
            "prefer_bus": prefer_bus,
            "profile": profile,
            "catalog": _catalog(pois),
        },
        ensure_ascii=False,
    )
    payload = {
        "model": LLM_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        response = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("LLM response content was not text")
    selection = LlmTourSelection.model_validate_json(content)
    catalog_ids = {poi.id for poi in pois}
    if any(stop_id not in catalog_ids for stop_id in selection.stop_ids):
        raise ValueError("LLM selected a stop outside the approved catalog")
    if len(selection.stop_ids) > max_stops:
        selection.stop_ids = selection.stop_ids[:max_stops]
    return selection
