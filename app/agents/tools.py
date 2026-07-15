"""Validated tools for the travel planning agent.

Every tool uses Pydantic for input validation AND output validation.
The LLM can call these tools; inputs are checked by Pydantic before the
function runs, outputs are validated before being returned to the LLM.
"""

import json
import math
import urllib.request
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from sqlalchemy import select, text

from app.agents.deps import TravelAgentDeps
from app.models.poi import POI
from app.models.stay import Stay


# ── POI Search ──

class POISearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Search query for POI names/descriptions")
    wilaya_id: int | None = Field(None, ge=1, le=58, description="Filter by wilaya ID")
    category: str | None = Field(None, description="Filter by category (historical, natural, cultural, museum, beach, etc.)")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class POISearchResult(BaseModel):
    id: str
    name: str
    category: str
    wilaya_id: int
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    entry_fee_dzd: float | None = None
    is_featured: bool = False


class POISearchOutput(BaseModel):
    results: list[POISearchResult]
    total: int


async def search_pois(ctx: RunContext[TravelAgentDeps], params: POISearchParams) -> POISearchOutput:
    """Search points of interest by query, wilaya, and/or category.

    Uses PostgreSQL full-text search to find relevant POIs.
    Returns matching POIs with their key details.
    """
    q = params.query.strip()
    conditions = ["search_vector @@ plainto_tsquery('french', :q)"]
    bind = {"q": q}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.category is not None:
        conditions.append("category = :category")
        bind["category"] = params.category

    where = " AND ".join(conditions)

    # Count
    count_sql = f"SELECT COUNT(*) FROM pois WHERE {where}"
    result = await ctx.deps.db.execute(text(count_sql), bind)
    total = result.scalar() or 0

    # Search
    sql = f"""
        SELECT id, name, category, wilaya_id, description,
               latitude, longitude, photo_url, entry_fee_dzd, is_featured
        FROM pois
        WHERE {where}
        ORDER BY is_featured DESC, ts_rank(search_vector, plainto_tsquery('french', :q)) DESC
        LIMIT :limit
    """
    bind["limit"] = params.limit
    result = await ctx.deps.db.execute(text(sql), bind)
    rows = result.all()

    return POISearchOutput(
        total=total,
        results=[
            POISearchResult(
                id=str(r[0]), name=r[1], category=r[2],
                wilaya_id=r[3], description=r[4],
                latitude=float(r[5]) if r[5] else None,
                longitude=float(r[6]) if r[6] else None,
                photo_url=r[7], entry_fee_dzd=float(r[8]) if r[8] else None,
                is_featured=r[9],
            )
            for r in rows
        ],
    )


# ── Stay Search ──

class StaySearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    wilaya_id: int | None = Field(None, ge=1, le=58)
    property_type: str | None = Field(None, description="hotel, guesthouse, hostel, eco_lodge, riad, apartment")
    max_price: float | None = Field(None, ge=0, description="Max price per night in DZD")
    limit: int = Field(10, ge=1, le=50)


class StaySearchResult(BaseModel):
    id: str
    name: str
    property_type: str
    wilaya_id: int
    price_per_night_dzd: float
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    amenities: list[str] | None = None
    max_guests: int | None = None


class StaySearchOutput(BaseModel):
    results: list[StaySearchResult]
    total: int


async def search_stays(ctx: RunContext[TravelAgentDeps], params: StaySearchParams) -> StaySearchOutput:
    """Search accommodations (hotels, guesthouses, hostels) by query, wilaya, type, and price.

    Finds places to stay matching the user's requirements.
    """
    q = params.query.strip()
    conditions = ["search_vector @@ plainto_tsquery('french', :q)"]
    bind = {"q": q}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.property_type is not None:
        conditions.append("property_type = :property_type")
        bind["property_type"] = params.property_type
    if params.max_price is not None:
        conditions.append("price_per_night_dzd <= :max_price")
        bind["max_price"] = params.max_price

    where = " AND ".join(conditions)

    result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM stays WHERE {where}"), bind
    )
    total = result.scalar() or 0

    sql = f"""
        SELECT id, name, property_type, wilaya_id, price_per_night_dzd,
               description, latitude, longitude, photos, amenities, max_guests
        FROM stays
        WHERE {where}
        ORDER BY ts_rank(search_vector, plainto_tsquery('french', :q)) DESC
        LIMIT :limit
    """
    bind["limit"] = params.limit
    result = await ctx.deps.db.execute(text(sql), bind)
    rows = result.all()

    return StaySearchOutput(
        total=total,
        results=[
            StaySearchResult(
                id=str(r[0]), name=r[1], property_type=r[2],
                wilaya_id=r[3], price_per_night_dzd=float(r[4]),
                description=r[5],
                latitude=float(r[6]) if r[6] else None,
                longitude=float(r[7]) if r[7] else None,
                photo_url=r[8][0] if r[8] else None,
                amenities=r[9], max_guests=r[10],
            )
            for r in rows
        ],
    )


# ── Experience Search ──

class ExperienceSearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    wilaya_id: int | None = Field(None, ge=1, le=58)
    category: str | None = Field(None, description="tour, workshop, homestay, hiking, cultural, food, adventure, wellness")
    season: str | None = Field(None, description="spring, summer, autumn, winter")
    limit: int = Field(10, ge=1, le=50)


class ExperienceSearchResult(BaseModel):
    id: str
    title: str
    category: str
    wilaya_id: int
    price_dzd: float | None = None
    duration_hours: float | None = None
    max_participants: int | None = None
    description: str | None = None
    meeting_point: str | None = None
    season: str | None = None
    photo_url: str | None = None


class ExperienceSearchOutput(BaseModel):
    results: list[ExperienceSearchResult]
    total: int


async def search_experiences(ctx: RunContext[TravelAgentDeps], params: ExperienceSearchParams) -> ExperienceSearchOutput:
    """Search tours, activities, and cultural experiences by query, wilaya, category, and season.

    Finds things to do: guided tours, cooking classes, hiking, wellness, etc.
    """
    q = params.query.strip()
    conditions = [
        "status = 'active'",
        "search_vector @@ plainto_tsquery('french', :q)",
    ]
    bind = {"q": q}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.category is not None:
        conditions.append("category = :category")
        bind["category"] = params.category
    if params.season is not None:
        conditions.append("season = :season")
        bind["season"] = params.season

    where = " AND ".join(conditions)

    result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM experiences WHERE {where}"), bind
    )
    total = result.scalar() or 0

    sql = f"""
        SELECT id, title, category, wilaya_id, price_dzd, duration_hours,
               max_participants, description, meeting_point, season, photos
        FROM experiences
        WHERE {where}
        ORDER BY ts_rank(search_vector, plainto_tsquery('french', :q)) DESC
        LIMIT :limit
    """
    bind["limit"] = params.limit
    result = await ctx.deps.db.execute(text(sql), bind)
    rows = result.all()

    return ExperienceSearchOutput(
        total=total,
        results=[
            ExperienceSearchResult(
                id=str(r[0]), title=r[1], category=r[2],
                wilaya_id=r[3], price_dzd=float(r[4]) if r[4] else None,
                duration_hours=float(r[5]) if r[5] else None,
                max_participants=r[6], description=r[7],
                meeting_point=r[8], season=r[9],
                photo_url=r[10][0] if r[10] else None,
            )
            for r in rows
        ],
    )


# ── Weather ──

class WeatherParams(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    date: str | None = Field(None, description="Date (YYYY-MM-DD) or blank for today")


class WeatherDay(BaseModel):
    date: str
    temp_max: float
    temp_min: float
    condition: str
    precipitation_mm: float


class WeatherOutput(BaseModel):
    location: dict = Field(default_factory=dict)
    days: list[WeatherDay]
    summary: str


async def get_weather(ctx: RunContext[TravelAgentDeps], params: WeatherParams) -> WeatherOutput:
    """Get weather forecast for a location (lat/lng) using Open-Meteo (free, no API key).

    Returns daily high/low temperatures, conditions, and precipitation.
    """
    target_date = params.date or date.today().isoformat()
    # Fetch 7 days around the target
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={params.latitude}&longitude={params.longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
        f"&timezone=auto&forecast_days=7"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ATHAR/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        return WeatherOutput(days=[], summary=f"Weather unavailable: {e}")

    daily = data.get("daily", {})
    times = daily.get("time", [])
    maxs = daily.get("temperature_2m_max", [])
    mins = daily.get("temperature_2m_min", [])
    precips = daily.get("precipitation_sum", [])
    codes = daily.get("weathercode", [])

    wmo_map = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
    }

    days = []
    for i in range(len(times)):
        code = codes[i] if i < len(codes) else 0
        days.append(WeatherDay(
            date=times[i],
            temp_max=float(maxs[i]) if i < len(maxs) else 0,
            temp_min=float(mins[i]) if i < len(mins) else 0,
            condition=wmo_map.get(int(code), f"Code {code}"),
            precipitation_mm=float(precips[i]) if i < len(precips) else 0,
        ))

    # Find closest day
    summary_parts = []
    for d in days:
        if d.date == target_date or (not summary_parts):
            summary_parts.append(
                f"{d.date}: {d.condition}, {d.temp_min}–{d.temp_max}°C, "
                f"{d.precipitation_mm}mm precipitation"
            )
            break

    return WeatherOutput(
        location={"lat": params.latitude, "lng": params.longitude},
        days=days,
        summary=" | ".join(summary_parts) if summary_parts else "No forecast available",
    )


# ── Collections ──

class CollectionSearchParams(BaseModel):
    collection_id: str = Field(..., description="UUID of the user's collection/wishlist")


class CollectionItemResult(BaseModel):
    entity_type: str
    entity_id: str
    notes: str | None = None


class CollectionSearchOutput(BaseModel):
    name: str
    items: list[CollectionItemResult]
    item_count: int


async def get_user_collection(ctx: RunContext[TravelAgentDeps], params: CollectionSearchParams) -> CollectionSearchOutput:
    """Get the contents of a user's saved collection (wishlist).

    Collections can contain POIs, stays, and experiences.
    """
    from app.models.collection import Collection as CollectionModel
    from sqlalchemy.orm import selectinload

    result = await ctx.deps.db.execute(
        select(CollectionModel)
        .where(
            CollectionModel.id == UUID(params.collection_id),
            CollectionModel.user_id == ctx.deps.user.id,
        )
        .options(selectinload(CollectionModel.items))
    )
    c = result.scalar_one_or_none()
    if not c:
        return CollectionSearchOutput(name="", items=[], item_count=0)

    return CollectionSearchOutput(
        name=c.name,
        item_count=len(c.items),
        items=[
            CollectionItemResult(entity_type=i.entity_type, entity_id=str(i.entity_id), notes=i.notes)
            for i in c.items
        ],
    )


# ── Wilaya Travel Guide ──

class WilayaGuideParams(BaseModel):
    wilaya_id: int = Field(..., ge=1, le=58, description="Wilaya ID (1-58)")
    top_per_category: int = Field(10, ge=1, le=50, description="Max POIs per category")


class GuidePOIOutput(BaseModel):
    id: str
    name: str
    category: str
    subtype: str | None = None
    description: str | None = None
    is_featured: bool = False
    entry_fee_dzd: float | None = None
    photo_url: str | None = None
    average_score: float | None = None
    total_reviews: int = 0
    nearest_station: str | None = None


class GuideCategoryOutput(BaseModel):
    category: str
    count: int
    pois: list[GuidePOIOutput]


class WilayaGuideOutput(BaseModel):
    wilaya_id: int
    wilaya_name: str
    description: str | None = None
    total_pois: int
    total_featured: int
    featured_pois: list[GuidePOIOutput]
    categories: list[GuideCategoryOutput]
    tips: list[str] = Field(default_factory=list)


async def get_wilaya_guide(ctx: RunContext[TravelAgentDeps], params: WilayaGuideParams) -> WilayaGuideOutput:
    """Get a curated travel guide for an Algerian wilaya.

    Returns featured attractions, top POIs by category, and travel tips.
    Use this when a user asks about what to see/do in a specific wilaya.
    """
    wid = params.wilaya_id
    top = params.top_per_category

    # Wilaya info
    w_row = await ctx.deps.db.execute(
        text("SELECT name_en, description, name_ar, latitude, longitude FROM wilayas WHERE id = :wid"),
        {"wid": wid},
    )
    w = w_row.one_or_none()
    if not w:
        return WilayaGuideOutput(
            wilaya_id=wid, wilaya_name=f"Wilaya {wid}",
            total_pois=0, total_featured=0,
            featured_pois=[], categories=[],
        )

    name = w[0] or w[2] or f"Wilaya {wid}"
    desc = w[1]

    # Total counts
    cnt = await ctx.deps.db.execute(
        text("SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_featured THEN 1 ELSE 0 END), 0) FROM pois WHERE wilaya_id = :wid"),
        {"wid": wid},
    )
    total_pois, total_featured = cnt.one()

    # Featured POIs
    featured = await ctx.deps.db.execute(
        text("""
            SELECT id, name, category, subtype, description, is_featured,
                   entry_fee_dzd, photo_url,
                   getting_there->>'nearest_station_name' as nearest_station
            FROM pois
            WHERE wilaya_id = :wid AND is_featured = true
            ORDER BY featured_order NULLS LAST
            LIMIT :top
        """),
        {"wid": wid, "top": top},
    )
    featured_pois = [
        GuidePOIOutput(
            id=str(r[0]), name=r[1], category=r[2], subtype=r[3],
            description=r[4], is_featured=r[5],
            entry_fee_dzd=float(r[6]) if r[6] else None,
            photo_url=r[7],
            nearest_station=r[8],
        )
        for r in featured.all()
    ]

    # Top POIs per category
    categories = []
    cat_rows = await ctx.deps.db.execute(
        text("""
            SELECT category, COUNT(*) as cnt
            FROM pois
            WHERE wilaya_id = :wid AND is_featured = false
            GROUP BY category
            ORDER BY cnt DESC
        """),
        {"wid": wid},
    )
    for cat_row in cat_rows.all():
        cat_name = cat_row[0]
        pois = await ctx.deps.db.execute(
            text("""
                SELECT id, name, category, subtype, description, is_featured,
                       entry_fee_dzd, photo_url,
                       getting_there->>'nearest_station_name' as nearest_station
                FROM pois
                WHERE wilaya_id = :wid AND category = :cat AND is_featured = false
                ORDER BY name
                LIMIT :top
            """),
            {"wid": wid, "cat": cat_name, "top": top},
        )
        categories.append(GuideCategoryOutput(
            category=cat_name,
            count=cat_row[1],
            pois=[
                GuidePOIOutput(
                    id=str(r[0]), name=r[1], category=r[2], subtype=r[3],
                    description=r[4], is_featured=r[5],
                    entry_fee_dzd=float(r[6]) if r[6] else None,
                    photo_url=r[7],
                    nearest_station=r[8],
                )
                for r in pois.all()
            ],
        ))

    # Travel tips based on wilaya characteristics
    tips = []
    if total_featured > 0:
        tips.append(f"There are {total_featured} must-see attractions in {name}.")
    if total_pois > 50:
        tips.append(f"With {total_pois} points of interest, plan at least 2-3 days to explore {name}.")

    return WilayaGuideOutput(
        wilaya_id=wid, wilaya_name=name, description=desc,
        total_pois=total_pois or 0, total_featured=total_featured or 0,
        featured_pois=featured_pois, categories=categories, tips=tips,
    )


# ── Transport Route ──

class TransportRouteParams(BaseModel):
    origin_wilaya_id: int = Field(..., ge=1, le=58, description="Departure wilaya ID")
    dest_wilaya_id: int = Field(..., ge=1, le=58, description="Destination wilaya ID")


class TransportModeOption(BaseModel):
    mode: str
    estimated_cost_dzd: float | None = None
    estimated_time_minutes: int | None = None
    time_label: str | None = None
    available: bool = True


class TransportRouteResult(BaseModel):
    origin_wilaya: str
    dest_wilaya: str
    driving_distance_km: float | None = None
    driving_time_minutes: int | None = None
    options: list[TransportModeOption]
    best_recommendation: str | None = None


async def get_transport_route(ctx: RunContext[TravelAgentDeps], params: TransportRouteParams) -> TransportRouteResult:
    """Get transport options between two Algerian wilayas.

    Returns cost + time estimates for bus, shared taxi, private taxi, train, and plane.
    Helpful when users ask how to get between cities or need travel budget planning.
    """
    from app.services.transport import TransportService

    svc = TransportService()
    route = await svc.get_route(ctx.deps.db, params.origin_wilaya_id, params.dest_wilaya_id)

    o_name, d_name = f"Wilaya {params.origin_wilaya_id}", f"Wilaya {params.dest_wilaya_id}"
    if route:
        o_name = route.origin_wilaya_id
        d_name = route.dest_wilaya_id

    if not route:
        return TransportRouteResult(
            origin_wilaya=o_name, dest_wilaya=d_name,
            options=[], best_recommendation="No transport route data available between these wilayas.",
        )

    options = []
    # Bus
    bus_cost = route.estimate_bus_cost()
    options.append(TransportModeOption(
        mode="bus", estimated_cost_dzd=bus_cost,
        estimated_time_minutes=route.driving_time_minutes,
        time_label=route.travel_time_label(),
    ))
    # Shared taxi
    shared_cost = route.estimate_shared_taxi_cost_per_person()
    options.append(TransportModeOption(
        mode="shared_taxi", estimated_cost_dzd=shared_cost,
        estimated_time_minutes=route.driving_time_minutes,
        time_label=route.travel_time_label(),
    ))
    # Private taxi
    priv_cost = route.estimate_private_taxi_cost()
    options.append(TransportModeOption(
        mode="private_taxi", estimated_cost_dzd=priv_cost,
        estimated_time_minutes=route.driving_time_minutes,
        time_label=route.travel_time_label(),
    ))
    # Train
    train_cost = route.estimate_train_cost()
    options.append(TransportModeOption(
        mode="train", estimated_cost_dzd=train_cost,
        available=train_cost is not None,
    ))
    # Plane
    plane_cost = route.estimate_plane_cost()
    options.append(TransportModeOption(
        mode="plane", estimated_cost_dzd=plane_cost,
        available=plane_cost is not None,
    ))

    # Best recommendation
    best = "bus"
    best_cost = bus_cost
    if shared_cost is not None and shared_cost < best_cost:
        best = "shared_taxi"
        best_cost = shared_cost
    if train_cost is not None and train_cost < best_cost:
        best = "train"
        best_cost = train_cost

    return TransportRouteResult(
        origin_wilaya=f"Wilaya {params.origin_wilaya_id}",
        dest_wilaya=f"Wilaya {params.dest_wilaya_id}",
        driving_distance_km=route.driving_distance_km,
        driving_time_minutes=route.driving_time_minutes,
        options=options,
        best_recommendation=f"The cheapest option is {best} at {best_cost:.0f} DZD per person.",
    )


# ── Events / Festivals ──

class EventSearchParams(BaseModel):
    wilaya_id: int | None = Field(None, ge=1, le=58, description="Filter by wilaya ID")
    category: str | None = Field(None, description="Filter by category: cultural, food, music, religious, adventure, etc.")
    month: int | None = Field(None, ge=1, le=12, description="Filter by month (1-12)")


class EventResult(BaseModel):
    id: str
    title: str
    wilaya_id: int
    category: str
    description: str | None = None
    month: int
    duration_days: int | None = None
    is_recurring: bool | None = None


class EventSearchOutput(BaseModel):
    results: list[EventResult]
    total: int


async def find_events(ctx: RunContext[TravelAgentDeps], params: EventSearchParams) -> EventSearchOutput:
    """Find cultural events and festivals in Algeria.

    Filter by wilaya, category (cultural, food, music, religious, adventure, hiking, beach),
    and month (1-12). Use this when users ask about festivals, events, or what's happening.
    """
    conditions: list[str] = []
    bind: dict = {}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.category is not None:
        conditions.append("category = :category")
        bind["category"] = params.category
    if params.month is not None:
        conditions.append("month = :month")
        bind["month"] = params.month

    where = " AND ".join(conditions) if conditions else "TRUE"

    result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM events WHERE {where}"), bind
    )
    total = result.scalar() or 0

    rows = await ctx.deps.db.execute(
        text(f"""
            SELECT id, title, wilaya_id, category, description, month,
                   duration_days, is_recurring
            FROM events
            WHERE {where}
            ORDER BY month, title
        """),
        bind,
    )

    return EventSearchOutput(
        total=total,
        results=[
            EventResult(
                id=str(r[0]), title=r[1], wilaya_id=r[2], category=r[3],
                description=r[4], month=r[5],
                duration_days=r[6], is_recurring=r[7],
            )
            for r in rows.all()
        ],
    )
