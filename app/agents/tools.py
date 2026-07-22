"""Validated tools for the travel planning agent.

Every tool uses Pydantic for input validation AND output validation.
The LLM can call these tools; inputs are checked by Pydantic before the
function runs, outputs are validated before being returned to the LLM.
"""

from datetime import date
from uuid import UUID

import httpx
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
    min_price: float | None = Field(None, ge=0, description="Min entry fee in DZD")
    max_price: float | None = Field(None, ge=0, description="Max entry fee in DZD")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class POISearchResult(BaseModel):
    id: str
    name: str
    name_ar: str | None = None
    name_en: str | None = None
    category: str
    subtype: str | None = None
    wilaya_id: int
    commune: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    entry_fee_dzd: float | None = None
    price_level: str | None = None
    is_featured: bool = False
    featured_order: int | None = None
    ranking_position: int | None = None
    ranking_total: int | None = None
    suggested_duration_min: int | None = None
    opening_hours: str | None = None
    phone: str | None = None
    website: str | None = None


class POISearchOutput(BaseModel):
    results: list[POISearchResult]
    total: int


async def search_pois(ctx: RunContext[TravelAgentDeps], params: POISearchParams) -> POISearchOutput:
    """Search points of interest by query, wilaya, and/or category.

    Uses PostgreSQL full-text search to find relevant POIs.
    Falls back to ILIKE name search when full-text returns no results.
    Returns matching POIs with key details including ranking, price level,
    duration, opening hours, and contact info.
    """
    q = params.query.strip()
    base_conditions = ["TRUE"]
    bind: dict = {}

    if params.wilaya_id is not None:
        base_conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.category is not None:
        base_conditions.append("category = :category")
        bind["category"] = params.category
    if params.min_price is not None:
        base_conditions.append("(entry_fee_dzd >= :min_price OR entry_fee_dzd IS NULL)")
        bind["min_price"] = params.min_price
    if params.max_price is not None:
        base_conditions.append("entry_fee_dzd <= :max_price")
        bind["max_price"] = params.max_price

    base_where = " AND ".join(base_conditions)
    columns = (
        "id, name, name_ar, name_en, category, subtype, wilaya_id, commune, "
        "description, latitude, longitude, photo_url, entry_fee_dzd, price_level, "
        "is_featured, featured_order, ranking_position, ranking_total, "
        "suggested_duration_min, opening_hours, phone, website"
    )

    # Try full-text search first
    ft_where = f"({base_where}) AND search_vector @@ plainto_tsquery('french', :q)"
    count_result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM pois WHERE {ft_where}"), {**bind, "q": q}
    )
    total = count_result.scalar() or 0

    if total > 0:
        sql = f"""
            SELECT {columns}
            FROM pois WHERE {ft_where}
            ORDER BY is_featured DESC, ranking_position NULLS LAST,
                     ts_rank(search_vector, plainto_tsquery('french', :q)) DESC
            LIMIT :limit
        """
        bind["q"] = q
        bind["limit"] = params.limit
        result = await ctx.deps.db.execute(text(sql), bind)
    else:
        # Fallback: ILIKE on name/name_en/name_ar/description
        ilike = f"%{q}%"
        ilike_where = (
            f"({base_where}) AND (name ILIKE :ilike OR name_en ILIKE :ilike "
            f"OR name_ar ILIKE :ilike OR description ILIKE :ilike)"
        )
        sql = f"""
            SELECT {columns}
            FROM pois WHERE {ilike_where}
            ORDER BY is_featured DESC, ranking_position NULLS LAST, name
            LIMIT :limit
        """
        bind["ilike"] = ilike
        bind["limit"] = params.limit
        result = await ctx.deps.db.execute(text(sql), bind)

    rows = result.all()

    return POISearchOutput(
        total=total,
        results=[
            POISearchResult(
                id=str(r[0]), name=r[1], name_ar=r[2], name_en=r[3],
                category=r[4], subtype=r[5], wilaya_id=r[6], commune=r[7],
                description=r[8],
                latitude=float(r[9]) if r[9] else None,
                longitude=float(r[10]) if r[10] else None,
                photo_url=r[11],
                entry_fee_dzd=float(r[12]) if r[12] else None,
                price_level=r[13], is_featured=r[14],
                featured_order=r[15], ranking_position=r[16],
                ranking_total=r[17],
                suggested_duration_min=r[18],
                opening_hours=r[19], phone=r[20], website=r[21],
            )
            for r in rows
        ],
    )


# ── Stay Search ──

class StaySearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    wilaya_id: int | None = Field(None, ge=1, le=58)
    property_type: str | None = Field(None, description="hotel, guesthouse, hostel, eco_lodge, riad, apartment")
    min_price: float | None = Field(None, ge=0, description="Min price per night in DZD")
    max_price: float | None = Field(None, ge=0, description="Max price per night in DZD")
    limit: int = Field(10, ge=1, le=50)


class StaySearchResult(BaseModel):
    id: str
    name: str
    property_type: str
    wilaya_id: int
    price_per_night_dzd: float
    description: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    amenities: list[str] | None = None
    max_guests: int | None = None
    check_in_time: str | None = None
    check_out_time: str | None = None


class StaySearchOutput(BaseModel):
    results: list[StaySearchResult]
    total: int


async def search_stays(ctx: RunContext[TravelAgentDeps], params: StaySearchParams) -> StaySearchOutput:
    """Search accommodations (hotels, guesthouses, hostels) by query, wilaya, type, and price.

    Only returns active stays. Includes address, check-in/out times.
    """
    q = params.query.strip()
    base_conditions = ["is_active = TRUE"]
    bind: dict = {"q": q}

    # Full-text search on stays
    conditions = ["is_active = TRUE", "search_vector @@ plainto_tsquery('french', :q)"]

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.property_type is not None:
        conditions.append("property_type = :property_type")
        bind["property_type"] = params.property_type
    if params.min_price is not None:
        conditions.append("price_per_night_dzd >= :min_price")
        bind["min_price"] = params.min_price
    if params.max_price is not None:
        conditions.append("price_per_night_dzd <= :max_price")
        bind["max_price"] = params.max_price

    where = " AND ".join(conditions)
    columns = (
        "id, name, property_type, wilaya_id, price_per_night_dzd, "
        "description, address, latitude, longitude, photos, amenities, "
        "max_guests, check_in_time, check_out_time"
    )

    count_result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM stays WHERE {where}"), bind
    )
    total = count_result.scalar() or 0

    if total > 0:
        sql = f"""
            SELECT {columns}
            FROM stays WHERE {where}
            ORDER BY ts_rank(search_vector, plainto_tsquery('french', :q)) DESC
            LIMIT :limit
        """
        bind["limit"] = params.limit
        result = await ctx.deps.db.execute(text(sql), bind)
    else:
        # Fallback: ILIKE
        ilike = f"%{q}%"
        conditions_fb = ["is_active = TRUE", "(name ILIKE :ilike OR description ILIKE :ilike)"]
        if params.wilaya_id is not None:
            conditions_fb.append("wilaya_id = :wilaya_id")
        if params.property_type is not None:
            conditions_fb.append("property_type = :property_type")
        if params.min_price is not None:
            conditions_fb.append("price_per_night_dzd >= :min_price")
        if params.max_price is not None:
            conditions_fb.append("price_per_night_dzd <= :max_price")
        where_fb = " AND ".join(conditions_fb)
        sql = f"""
            SELECT {columns}
            FROM stays WHERE {where_fb}
            ORDER BY name
            LIMIT :limit
        """
        bind["ilike"] = ilike
        bind["limit"] = params.limit
        result = await ctx.deps.db.execute(text(sql), bind)

    rows = result.all()

    return StaySearchOutput(
        total=total,
        results=[
            StaySearchResult(
                id=str(r[0]), name=r[1], property_type=r[2],
                wilaya_id=r[3], price_per_night_dzd=float(r[4]),
                description=r[5], address=r[6],
                latitude=float(r[7]) if r[7] else None,
                longitude=float(r[8]) if r[8] else None,
                photo_url=r[9][0] if r[9] else None,
                amenities=r[10], max_guests=r[11],
                check_in_time=r[12], check_out_time=r[13],
            )
            for r in rows
        ],
    )


# ── Experience Search ──

class ExperienceSearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    wilaya_id: int | None = Field(None, ge=1, le=58)
    category: str | None = Field(None, description="tour, workshop, homestay, hiking, cultural, food, adventure, wellness")
    season: str | None = Field(None, description="spring, summer, autumn, winter (or month number 1-12)")
    min_price: float | None = Field(None, ge=0, description="Min price in DZD")
    max_price: float | None = Field(None, ge=0, description="Max price in DZD")
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
    included: list[str] | None = None
    what_to_bring: list[str] | None = None
    language: str | None = None
    is_verified: bool = False
    completion_count: int = 0


class ExperienceSearchOutput(BaseModel):
    results: list[ExperienceSearchResult]
    total: int


_MONTH_TO_SEASON = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "spring", 6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
}


async def search_experiences(ctx: RunContext[TravelAgentDeps], params: ExperienceSearchParams) -> ExperienceSearchOutput:
    """Search tours, activities, and cultural experiences by query, wilaya, category, and season.

    Season can be a word (spring/summer/autumn/winter) or a month number (1-12).
    Includes included items, what-to-bring, language, and completion count.
    """
    q = params.query.strip()
    conditions = [
        "status = 'active'",
        "search_vector @@ plainto_tsquery('french', :q)",
    ]
    bind: dict = {"q": q}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.category is not None:
        conditions.append("category = :category")
        bind["category"] = params.category
    if params.min_price is not None:
        conditions.append("price_dzd >= :min_price")
        bind["min_price"] = params.min_price
    if params.max_price is not None:
        conditions.append("price_dzd <= :max_price")
        bind["max_price"] = params.max_price
    if params.season is not None:
        # Accept month numbers and convert to season
        season_val = params.season.strip()
        if season_val.isdigit() and 1 <= int(season_val) <= 12:
            conditions.append("season = :season")
            bind["season"] = _MONTH_TO_SEASON[int(season_val)]
        else:
            conditions.append("season = :season")
            bind["season"] = season_val

    where = " AND ".join(conditions)
    columns = (
        "id, title, category, wilaya_id, price_dzd, duration_hours, "
        "max_participants, description, meeting_point, season, photos, "
        "included, what_to_bring, language, is_verified, completion_count"
    )

    count_result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM experiences WHERE {where}"), bind
    )
    total = count_result.scalar() or 0

    sql = f"""
        SELECT {columns}
        FROM experiences WHERE {where}
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
                included=r[11], what_to_bring=r[12],
                language=r[13], is_verified=r[14] or False,
                completion_count=r[15] or 0,
            )
            for r in rows
        ],
    )


# ── Artisan Search ──

class ArtisanSearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Search query for artisan name/craft")
    wilaya_id: int | None = Field(None, ge=1, le=58, description="Filter by wilaya ID")
    craft_type: str | None = Field(None, description="Filter by craft type (pottery, carpet_weaving, jewelry, etc.)")
    has_workshop: bool | None = Field(None, description="Only show artisans with workshops")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class ArtisanSearchResult(BaseModel):
    id: str
    name: str
    craft_type: str
    wilaya_id: int
    description: str | None = None
    address: str | None = None
    commune: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    photo_url: str | None = None
    years_experience: int | None = None
    specializations: list[str] | None = None
    price_range_min: float | None = None
    price_range_max: float | None = None
    accepts_visitors: bool = True
    has_workshop: bool = True
    is_verified: bool = False


class ArtisanSearchOutput(BaseModel):
    results: list[ArtisanSearchResult]
    total: int


async def search_artisans(ctx: RunContext[TravelAgentDeps], params: ArtisanSearchParams) -> ArtisanSearchOutput:
    """Search artisans/craftspeople by name, craft type, and wilaya.

    Returns artisans with full contact details, workshop info, and pricing.
    """
    q = params.query.strip()
    conditions = ["(name ILIKE :q OR craft_type ILIKE :q OR description ILIKE :q OR specializations::text ILIKE :q)"]
    bind: dict = {"q": f"%{q}%"}

    if params.wilaya_id is not None:
        conditions.append("wilaya_id = :wilaya_id")
        bind["wilaya_id"] = params.wilaya_id
    if params.craft_type is not None:
        conditions.append("craft_type = :craft_type")
        bind["craft_type"] = params.craft_type
    if params.has_workshop is not None:
        conditions.append("has_workshop = :has_workshop")
        bind["has_workshop"] = params.has_workshop

    where = " AND ".join(conditions)
    columns = (
        "id, name, craft_type, wilaya_id, description, address, commune, "
        "latitude, longitude, phone, whatsapp, website, photos, "
        "years_experience, specializations, price_range_min, price_range_max, "
        "accepts_visitors, has_workshop, is_verified"
    )

    count_result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM artisans WHERE {where}"), bind
    )
    total = count_result.scalar() or 0

    sql = f"""
        SELECT {columns}
        FROM artisans WHERE {where}
        ORDER BY is_verified DESC, years_experience DESC NULLS LAST
        LIMIT :limit
    """
    bind["limit"] = params.limit
    result = await ctx.deps.db.execute(text(sql), bind)
    rows = result.all()

    return ArtisanSearchOutput(
        total=total,
        results=[
            ArtisanSearchResult(
                id=str(r[0]), name=r[1], craft_type=r[2],
                wilaya_id=r[3], description=r[4],
                address=r[5], commune=r[6],
                latitude=r[7], longitude=r[8],
                phone=r[9], whatsapp=r[10], website=r[11],
                photo_url=r[12][0] if r[12] else None,
                years_experience=r[13],
                specializations=r[14],
                price_range_min=float(r[15]) if r[15] else None,
                price_range_max=float(r[16]) if r[16] else None,
                accepts_visitors=r[17] if r[17] is not None else True,
                has_workshop=r[18] if r[18] is not None else True,
                is_verified=r[19] or False,
            )
            for r in rows
        ],
    )


# ── Weather ──

WMO_MAP = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


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
    Summary covers all forecast days.
    """
    target_date = params.date or date.today().isoformat()
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={params.latitude}&longitude={params.longitude}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
        "&timezone=auto&forecast_days=7"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"User-Agent": "ATHAR/1.0"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return WeatherOutput(days=[], summary=f"Weather unavailable: {e}")

    daily = data.get("daily", {})
    times = daily.get("time", [])
    maxs = daily.get("temperature_2m_max", [])
    mins = daily.get("temperature_2m_min", [])
    precips = daily.get("precipitation_sum", [])
    codes = daily.get("weathercode", [])

    days = []
    for i in range(len(times)):
        code = codes[i] if i < len(codes) else 0
        days.append(WeatherDay(
            date=times[i],
            temp_max=float(maxs[i]) if i < len(maxs) else 0,
            temp_min=float(mins[i]) if i < len(mins) else 0,
            condition=WMO_MAP.get(int(code), f"Code {code}"),
            precipitation_mm=float(precips[i]) if i < len(precips) else 0,
        ))

    # Build summary covering all days
    summary_parts = []
    for d in days:
        summary_parts.append(
            f"{d.date}: {d.condition}, {d.temp_min:.0f}–{d.temp_max:.0f}°C"
            + (f", {d.precipitation_mm:.1f}mm rain" if d.precipitation_mm > 0 else "")
        )

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
    price_level: str | None = None
    suggested_duration_min: int | None = None
    photo_url: str | None = None
    average_score: float | None = None
    total_reviews: int = 0
    nearest_station: str | None = None


class GuideCategoryOutput(BaseModel):
    category: str
    count: int
    pois: list[GuidePOIOutput]


class GuideStaySummary(BaseModel):
    id: str
    name: str
    property_type: str
    price_per_night_dzd: float
    photo_url: str | None = None


class GuideExperienceSummary(BaseModel):
    id: str
    title: str
    category: str
    price_dzd: float | None = None
    duration_hours: float | None = None
    photo_url: str | None = None


class GuideEventSummary(BaseModel):
    id: str
    title: str
    category: str
    month: int
    duration_days: int | None = None
    photo_url: str | None = None


class WilayaGuideOutput(BaseModel):
    wilaya_id: int
    wilaya_name: str
    description: str | None = None
    total_pois: int
    total_featured: int
    total_stays: int = 0
    total_experiences: int = 0
    total_events: int = 0
    featured_pois: list[GuidePOIOutput]
    categories: list[GuideCategoryOutput]
    top_stays: list[GuideStaySummary] = Field(default_factory=list)
    top_experiences: list[GuideExperienceSummary] = Field(default_factory=list)
    upcoming_events: list[GuideEventSummary] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


async def _lookup_wilaya_names(ctx: RunContext[TravelAgentDeps], ids: list[int]) -> dict[int, str]:
    """Look up wilaya English names for a set of IDs."""
    if not ids:
        return {}
    placeholders = ", ".join(f":w{i}" for i in range(len(ids)))
    bind = {f"w{i}": wid for i, wid in enumerate(ids)}
    rows = await ctx.deps.db.execute(
        text(f"SELECT id, name_en FROM wilayas WHERE id IN ({placeholders})"), bind
    )
    return {r[0]: r[1] for r in rows.all()}


async def get_wilaya_guide(ctx: RunContext[TravelAgentDeps], params: WilayaGuideParams) -> WilayaGuideOutput:
    """Get a curated travel guide for an Algerian wilaya.

    Returns featured attractions, top POIs by category (sorted by ranking),
    top stays, active experiences, upcoming events, and travel tips.
    Use this when a user asks about what to see/do in a specific wilaya.
    """
    wid = params.wilaya_id
    top = params.top_per_category

    # Wilaya info
    w_row = await ctx.deps.db.execute(
        text("SELECT name_en, description, name_ar FROM wilayas WHERE id = :wid"),
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

    # Stay / Experience / Event counts
    stays_cnt = await ctx.deps.db.execute(
        text("SELECT COUNT(*) FROM stays WHERE wilaya_id = :wid AND is_active = TRUE"), {"wid": wid}
    )
    total_stays = stays_cnt.scalar() or 0

    exp_cnt = await ctx.deps.db.execute(
        text("SELECT COUNT(*) FROM experiences WHERE wilaya_id = :wid AND status = 'active'"), {"wid": wid}
    )
    total_experiences = exp_cnt.scalar() or 0

    evt_cnt = await ctx.deps.db.execute(
        text("SELECT COUNT(*) FROM events WHERE wilaya_id = :wid"), {"wid": wid}
    )
    total_events = evt_cnt.scalar() or 0

    # Featured POIs
    featured = await ctx.deps.db.execute(
        text("""
            SELECT id, name, category, subtype, description, is_featured,
                   entry_fee_dzd, price_level, suggested_duration_min,
                   photo_url,
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
            price_level=r[7], suggested_duration_min=r[8],
            photo_url=r[9],
            nearest_station=r[10],
        )
        for r in featured.all()
    ]

    # Top POIs per category — sorted by ranking_position (quality), then name
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
                       entry_fee_dzd, price_level, suggested_duration_min,
                       photo_url,
                       getting_there->>'nearest_station_name' as nearest_station
                FROM pois
                WHERE wilaya_id = :wid AND category = :cat AND is_featured = false
                ORDER BY ranking_position NULLS LAST, name
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
                    price_level=r[7], suggested_duration_min=r[8],
                    photo_url=r[9],
                    nearest_station=r[10],
                )
                for r in pois.all()
            ],
        ))

    # Top stays
    stays_rows = await ctx.deps.db.execute(
        text("""
            SELECT id, name, property_type, price_per_night_dzd, photos
            FROM stays
            WHERE wilaya_id = :wid AND is_active = TRUE
            ORDER BY price_per_night_dzd
            LIMIT 5
        """),
        {"wid": wid},
    )
    top_stays = [
        GuideStaySummary(
            id=str(r[0]), name=r[1], property_type=r[2],
            price_per_night_dzd=float(r[3]),
            photo_url=r[4][0] if r[4] else None,
        )
        for r in stays_rows.all()
    ]

    # Top experiences
    exp_rows = await ctx.deps.db.execute(
        text("""
            SELECT id, title, category, price_dzd, duration_hours, photos
            FROM experiences
            WHERE wilaya_id = :wid AND status = 'active'
            ORDER BY completion_count DESC
            LIMIT 5
        """),
        {"wid": wid},
    )
    top_experiences = [
        GuideExperienceSummary(
            id=str(r[0]), title=r[1], category=r[2],
            price_dzd=float(r[3]) if r[3] else None,
            duration_hours=float(r[4]) if r[4] else None,
            photo_url=r[5][0] if r[5] else None,
        )
        for r in exp_rows.all()
    ]

    # Upcoming events (current month + next)
    current_month = date.today().month
    next_month = (current_month % 12) + 1
    evt_rows = await ctx.deps.db.execute(
        text("""
            SELECT id, title, category, month, duration_days, photo_url
            FROM events
            WHERE wilaya_id = :wid AND month IN (:m1, :m2)
            ORDER BY month, title
            LIMIT 5
        """),
        {"wid": wid, "m1": current_month, "m2": next_month},
    )
    upcoming_events = [
        GuideEventSummary(
            id=str(r[0]), title=r[1], category=r[2], month=r[3],
            duration_days=r[4], photo_url=r[5],
        )
        for r in evt_rows.all()
    ]

    # Travel tips
    tips = []
    if total_featured > 0:
        tips.append(f"There are {total_featured} must-see attractions in {name}.")
    if total_pois > 50:
        tips.append(f"With {total_pois} points of interest, plan at least 2-3 days to explore {name}.")
    if total_stays > 0:
        tips.append(f"{total_stays} accommodations available, from budget to mid-range.")
    if total_experiences > 0:
        tips.append(f"{total_experiences} bookable experiences including tours, workshops, and hikes.")
    if total_events > 0:
        tips.append(f"{total_events} cultural events and festivals throughout the year.")

    return WilayaGuideOutput(
        wilaya_id=wid, wilaya_name=name, description=desc,
        total_pois=total_pois or 0, total_featured=total_featured or 0,
        total_stays=total_stays, total_experiences=total_experiences,
        total_events=total_events,
        featured_pois=featured_pois, categories=categories,
        top_stays=top_stays, top_experiences=top_experiences,
        upcoming_events=upcoming_events, tips=tips,
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
    origin_wilaya_id: int
    dest_wilaya_id: int
    driving_distance_km: float | None = None
    driving_time_minutes: int | None = None
    options: list[TransportModeOption]
    best_recommendation: str | None = None


async def get_transport_route(ctx: RunContext[TravelAgentDeps], params: TransportRouteParams) -> TransportRouteResult:
    """Get transport options between two Algerian wilayas.

    Returns cost + time estimates for bus, shared taxi, private taxi, train, and plane.
    Includes actual wilaya names for the origin and destination.
    """
    from app.services.transport import TransportService

    # Look up wilaya names
    names = await _lookup_wilaya_names(ctx, [params.origin_wilaya_id, params.dest_wilaya_id])
    o_name = names.get(params.origin_wilaya_id, f"Wilaya {params.origin_wilaya_id}")
    d_name = names.get(params.dest_wilaya_id, f"Wilaya {params.dest_wilaya_id}")

    svc = TransportService()
    route = await svc.get_route(ctx.deps.db, params.origin_wilaya_id, params.dest_wilaya_id)

    if not route:
        return TransportRouteResult(
            origin_wilaya=o_name, dest_wilaya=d_name,
            origin_wilaya_id=params.origin_wilaya_id,
            dest_wilaya_id=params.dest_wilaya_id,
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
        origin_wilaya=o_name, dest_wilaya=d_name,
        origin_wilaya_id=params.origin_wilaya_id,
        dest_wilaya_id=params.dest_wilaya_id,
        driving_distance_km=route.driving_distance_km,
        driving_time_minutes=route.driving_time_minutes,
        options=options,
        best_recommendation=f"The cheapest option is {best} at {best_cost:.0f} DZD per person.",
    )


# ── Events / Festivals ──

class EventSearchParams(BaseModel):
    wilaya_id: int | None = Field(None, ge=1, le=58, description="Filter by wilaya ID")
    category: str | None = Field(None, description="Filter by category: cultural, food, music, religious, adventure, hiking, beach")
    month: int | None = Field(None, ge=1, le=12, description="Filter by month (1-12)")
    query: str | None = Field(None, max_length=200, description="Text search on title/description")
    limit: int = Field(20, ge=1, le=50, description="Max results to return")


class EventResult(BaseModel):
    id: str
    title: str
    wilaya_id: int
    category: str
    description: str | None = None
    month: int
    duration_days: int | None = None
    is_recurring: bool | None = None
    photo_url: str | None = None


class EventSearchOutput(BaseModel):
    results: list[EventResult]
    total: int


async def find_events(ctx: RunContext[TravelAgentDeps], params: EventSearchParams) -> EventSearchOutput:
    """Find cultural events and festivals in Algeria.

    Filter by wilaya, category (cultural, food, music, religious, adventure, hiking, beach),
    month (1-12), and text search on title/description. Use this when users ask about
    festivals, events, or what's happening in a region.
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
    if params.query:
        conditions.append("(title ILIKE :q OR description ILIKE :q)")
        bind["q"] = f"%{params.query.strip()}%"

    where = " AND ".join(conditions) if conditions else "TRUE"

    count_result = await ctx.deps.db.execute(
        text(f"SELECT COUNT(*) FROM events WHERE {where}"), bind
    )
    total = count_result.scalar() or 0

    rows = await ctx.deps.db.execute(
        text(f"""
            SELECT id, title, wilaya_id, category, description, month,
                   duration_days, is_recurring, photo_url
            FROM events
            WHERE {where}
            ORDER BY month, title
            LIMIT :limit
        """),
        {**bind, "limit": params.limit},
    )

    return EventSearchOutput(
        total=total,
        results=[
            EventResult(
                id=str(r[0]), title=r[1], wilaya_id=r[2], category=r[3],
                description=r[4], month=r[5],
                duration_days=r[6], is_recurring=r[7],
                photo_url=r[8],
            )
            for r in rows.all()
        ],
    )
