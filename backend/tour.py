from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from .router import haversine_m

TourIntentType = Literal["plan_tour", "change_route_preference", "unknown"]
TourCategory = Literal["history", "food", "culture", "nature", "shopping", "family", "viewpoint", "museum", "religion"]
TourProfile = Literal["normal", "avoid_stairs", "luggage", "stroller", "wheelchair"]


class TourRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    start_lat: float | None = Field(None, ge=-90, le=90)
    start_lon: float | None = Field(None, ge=-180, le=180)
    start_name: str | None = Field(None, max_length=200)
    end_lat: float | None = Field(None, ge=-90, le=90)
    end_lon: float | None = Field(None, ge=-180, le=180)
    end_name: str | None = Field(None, max_length=200)
    available_minutes: int | None = Field(None, ge=30, le=1440)
    max_stops: int = Field(5, ge=1, le=10)
    prefer_bus: bool = False
    profile: TourProfile = "normal"
    max_walk_km: float | None = Field(None, ge=0, le=100)


class TourStop(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    category: TourCategory
    stay_minutes: int = Field(..., ge=5, le=240)
    reason: str
    source: str = "curated"


class TourLeg(BaseModel):
    start_stop_id: str
    end_stop_id: str
    distance_m: float = Field(..., ge=0)
    duration_minutes: float = Field(..., ge=0)
    mode: Literal["walk", "bus"] = "walk"
    route_available: bool
    warning: str | None = None


class TourPlan(BaseModel):
    intent: TourIntentType
    purpose: str
    categories: list[TourCategory]
    stops: list[TourStop]
    legs: list[TourLeg]
    total_distance_m: float = Field(..., ge=0)
    total_duration_minutes: float = Field(..., ge=0)
    needs_clarification: bool = False
    clarification_question: str | None = None
    needs_confirmation: bool = True
    warnings: list[str] = Field(default_factory=list)
    source: Literal["rules", "llm"] = "rules"


class LlmTourSelection(BaseModel):
    """The only part of a tour plan accepted from an external model."""

    purpose: str = Field(..., min_length=1, max_length=500)
    categories: list[TourCategory] = Field(default_factory=list, max_length=9)
    stop_ids: list[str] = Field(..., min_length=1, max_length=10)
    stay_minutes: dict[str, int] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)


class TourRouteRequest(BaseModel):
    stops: list[TourStop] = Field(..., min_length=2, max_length=10)
    prefer_bus: bool = False
    profile: TourProfile = "normal"
    max_slope: float | None = Field(None, ge=0, le=100)


class TourRouteResponse(BaseModel):
    success: bool
    stops: list[TourStop]
    legs: list[TourLeg]
    coordinates: list[list[float]]
    total_distance_m: float = Field(..., ge=0)
    total_duration_minutes: float = Field(..., ge=0)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Poi:
    id: str
    name: str
    latitude: float
    longitude: float
    category: TourCategory
    stay_minutes: int
    reason: str


# These are planning candidates, not claims about live opening hours.
POIS = (
    Poi("ruins_of_st_paul", "大三巴牌坊", 22.1971, 113.5408, "history", 45, "澳门代表性历史地标"),
    Poi("macau_museum", "澳门博物馆", 22.1971, 113.5376, "museum", 60, "了解澳门历史与文化"),
    Poi("senado_square", "议事亭前地", 22.1934, 113.5395, "culture", 30, "适合步行观光和拍照"),
    Poi("a_ma_temple", "妈阁庙", 22.1874, 113.5318, "religion", 45, "澳门重要历史宗教景点"),
    Poi("monte_fort", "大炮台", 22.1970, 113.5382, "viewpoint", 40, "可观赏澳门城市景观"),
    Poi("taipa_village", "氹仔旧城区", 22.1558, 113.5580, "history", 60, "适合体验旧城区与葡式建筑"),
    Poi("coloane_village", "路环村", 22.1156, 113.5512, "nature", 60, "适合慢行和海边观光"),
    Poi("macau_food_area", "澳门半岛美食街区", 22.1948, 113.5378, "food", 75, "安排澳门地方美食体验"),
)


def parse_tour_intent(text: str) -> tuple[str, list[TourCategory], int | None, int]:
    normalized = text.lower()
    category_keywords: dict[TourCategory, tuple[str, ...]] = {
        "history": ("历史", "古迹", "文化遗产", "historic"),
        "food": ("美食", "吃", "餐厅", "小吃", "food"),
        "culture": ("文化", "博物馆", "culture"),
        "nature": ("自然", "海边", "公园", "nature"),
        "shopping": ("购物", "shopping"),
        "family": ("亲子", "小孩", "family"),
        "viewpoint": ("拍照", "景色", "观景", "view"),
        "museum": ("博物馆", "museum"),
        "religion": ("寺", "庙", "宗教", "religion"),
    }
    categories = [category for category, words in category_keywords.items() if any(word in normalized for word in words)]
    if not categories:
        categories = ["history", "food"]
    duration_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|小時|hour|hours|h)", normalized)
    available_minutes = int(float(duration_match.group(1)) * 60) if duration_match else None
    stop_match = re.search(r"(\d+)\s*(?:个|個|站|景点|景點|stops?)", normalized)
    max_stops = max(1, min(int(stop_match.group(1)), 10)) if stop_match else 5
    return text.strip(), categories, available_minutes, max_stops


def candidate_pois(categories: list[TourCategory], max_stops: int) -> list[Poi]:
    ranked = sorted(
        POIS,
        key=lambda poi: (0 if poi.category in categories else 1, poi.stay_minutes),
    )
    return ranked[:max_stops]
