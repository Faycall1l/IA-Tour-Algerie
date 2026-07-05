import uuid

from langchain.tools import tool
from sqlalchemy import select

from app.models.experience import Experience
from app.models.poi import POI
from app.models.price_report import PriceReport
from app.models.review import Review
from app.models.stay import Stay
from app.services.agent.session import get_tool_context


@tool
async def search_pois(
    query: str,
    wilaya_id: int | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search points of interest. Optionally filter by wilaya_id or category."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return []
    stmt = select(POI)
    if wilaya_id is not None:
        stmt = stmt.where(POI.wilaya_id == wilaya_id)
    if category is not None:
        stmt = stmt.where(POI.category == category)
    stmt = stmt.limit(limit)
    rows = (await ctx.db_session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "category": p.category,
            "wilaya_id": p.wilaya_id,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "entry_fee_dzd": p.entry_fee_dzd,
            "description": p.description,
            "photo_url": p.photo_url,
        }
        for p in rows
    ]


@tool
async def get_price_estimate(
    item_type: str,
    item_id: str,
) -> dict:
    """Get fair price estimate for a POI or experience."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return {"min": None, "max": None, "median": None, "count": 0}
    uid = uuid.UUID(item_id)
    rows = (
        await ctx.db_session.execute(
            select(PriceReport.price_dzd).where(PriceReport.poi_id == uid).limit(20)
        )
    ).all()
    prices = [r[0] for r in rows]
    if not prices:
        return {"min": None, "max": None, "median": None, "count": 0}
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    if n % 2:
        median = sorted_prices[n // 2]
    else:
        median = (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
    return {
        "min": min(prices),
        "max": max(prices),
        "median": round(median, 0),
        "count": n,
    }


@tool
async def get_review_summary(
    item_type: str,
    item_id: str,
) -> dict:
    """Get aggregated review scores and count for a POI."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return {"average_score": None, "total_reviews": 0}
    uid = uuid.UUID(item_id)
    rows = (
        await ctx.db_session.execute(select(Review.overall_score).where(Review.poi_id == uid))
    ).all()
    scores = [r[0] for r in rows]
    if not scores:
        return {"average_score": None, "total_reviews": 0}
    return {
        "average_score": round(sum(scores) / len(scores), 1),
        "total_reviews": len(scores),
    }


@tool
async def get_experience(
    experience_id: str,
) -> dict | None:
    """Get details of a bookable experience."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return None
    exp = await ctx.db_session.get(Experience, uuid.UUID(experience_id))
    if exp is None:
        return None
    return {
        "id": str(exp.id),
        "title": exp.title,
        "category": exp.category,
        "wilaya_id": exp.wilaya_id,
        "price_dzd": exp.price_dzd,
        "duration_hours": exp.duration_hours,
        "meeting_point_lat": exp.meeting_point_lat,
        "meeting_point_lng": exp.meeting_point_lng,
        "status": exp.status,
    }


@tool
async def get_stay(
    stay_id: str,
) -> dict | None:
    """Get accommodation details."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return None
    stay = await ctx.db_session.get(Stay, uuid.UUID(stay_id))
    if stay is None:
        return None
    return {
        "id": str(stay.id),
        "name": stay.name,
        "property_type": stay.property_type,
        "wilaya_id": stay.wilaya_id,
        "price_per_night_dzd": stay.price_per_night_dzd,
        "amenities": stay.amenities,
        "max_guests": stay.max_guests,
        "latitude": stay.latitude,
        "longitude": stay.longitude,
    }


@tool
async def compute_travel_time(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    mode: str = "walking",
) -> dict:
    """Estimate travel time between two coordinates. Returns km and minutes."""
    import math

    radius = 6371
    dlat = math.radians(dest_lat - origin_lat)
    dlng = math.radians(dest_lng - origin_lng)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(origin_lat))
        * math.cos(math.radians(dest_lat))
        * math.sin(dlng / 2) ** 2
    )
    dist_km = radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    speed_kmh = 5 if mode == "walking" else 50 if mode == "driving" else 20
    minutes = int(dist_km / speed_kmh * 60)
    return {"distance_km": round(dist_km, 1), "duration_minutes": minutes, "mode": mode}


@tool
async def find_nearby(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    types: str = "poi,experience,stay",
    limit: int = 5,
) -> list[dict]:
    """Find items near a location. Types: comma-separated poi,experience,stay."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return []
    results: list[dict] = []
    item_types = [t.strip() for t in types.split(",")]

    if "poi" in item_types:
        rows = (await ctx.db_session.execute(select(POI).limit(limit))).scalars().all()
        for p in rows:
            if p.latitude and p.longitude:
                dist = _haversine(lat, lng, p.latitude, p.longitude)
                if dist <= radius_km:
                    results.append(
                        {
                            "id": str(p.id),
                            "name": p.name,
                            "type": "poi",
                            "distance_km": round(dist, 1),
                        }
                    )

    return sorted(results, key=lambda x: x["distance_km"])[:limit]


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
