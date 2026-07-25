import uuid

from langchain.tools import tool
from sqlalchemy import select

from app.models.experience import Experience
from app.models.poi import POI

from app.models.stay import Stay
from app.services.agent.session import get_tool_context
from app.services.transport import TransportService


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
async def get_transport_route(
    origin_wilaya_id: int,
    dest_wilaya_id: int,
) -> dict:
    """Get real road distance, driving time, and transport cost estimates between two wilayas."""
    ctx = get_tool_context()
    if ctx.db_session is None:
        return {"error": "no database session"}
    svc = TransportService()
    route = await svc.get_route(ctx.db_session, origin_wilaya_id, dest_wilaya_id)
    if route is None:
        return {"error": "no route found"}
    result = {
        "origin_wilaya_id": origin_wilaya_id,
        "dest_wilaya_id": dest_wilaya_id,
        "driving_distance_km": route.driving_distance_km,
        "driving_time_minutes": route.driving_time_minutes,
        "road_classification": route.road_classification,
        "estimated_costs_dzd": {
            "bus": route.estimate_bus_cost(),
            "shared_taxi": route.estimate_shared_taxi_cost(),
            "private_taxi": route.estimate_private_taxi_cost(),
        },
    }
    train = route.estimate_train_cost()
    if train is not None:
        result["estimated_costs_dzd"]["train"] = train
    plane = route.estimate_plane_cost()
    if plane is not None:
        result["estimated_costs_dzd"]["plane"] = plane
    return result


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
