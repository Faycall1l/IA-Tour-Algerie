import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.experience import Experience
from app.models.poi import POI
from app.models.stay import Stay

logger = logging.getLogger(__name__)
router = APIRouter(tags=["GeoJSON"])


def feature(props: dict, lat: float, lng: float) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": props,
    }


def fc(features: list) -> dict:
    return {"type": "FeatureCollection", "features": features}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get(
    "/pois.geojson",
    summary="POIs as GeoJSON",
    description="All geolocated POIs as a GeoJSON FeatureCollection of points, filtered by wilaya, category, or featured status.",
    responses={
        422: {"description": "Invalid filter or limit"},
        200: {"description": "GeoJSON FeatureCollection"},
    },
)
async def pois_geojson(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
    is_featured: bool | None = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
):
    cols = [POI.id, POI.name, POI.category, POI.latitude, POI.longitude,
            POI.photo_url, POI.wilaya_id, POI.subtype, POI.is_featured]
    query = select(*cols).where(POI.latitude.isnot(None), POI.longitude.isnot(None))
    if wilaya_id is not None:
        query = query.where(POI.wilaya_id == wilaya_id)
    if category is not None:
        query = query.where(POI.category == category)
    if is_featured is not None:
        query = query.where(POI.is_featured == is_featured)
    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return fc([
        feature(
            {"id": str(r.id), "name": r.name, "category": r.category,
             "wilaya_id": r.wilaya_id, "subtype": r.subtype,
             "photo_url": r.photo_url, "is_featured": r.is_featured},
            float(r.latitude), float(r.longitude),
        )
        for r in rows
    ])


@router.get(
    "/stays.geojson",
    summary="Stays as GeoJSON",
    description="All geolocated stays as a GeoJSON FeatureCollection, filtered by wilaya. Each feature carries the primary photo URL.",
    responses={
        422: {"description": "Invalid filter or limit"},
        200: {"description": "GeoJSON FeatureCollection"},
    },
)
async def stays_geojson(
    wilaya_id: int | None = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
):
    cols = [Stay.id, Stay.name, Stay.property_type, Stay.latitude, Stay.longitude,
            Stay.photos, Stay.wilaya_id]
    query = select(*cols).where(Stay.latitude.isnot(None), Stay.longitude.isnot(None))
    if wilaya_id is not None:
        query = query.where(Stay.wilaya_id == wilaya_id)
    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return fc([
        feature(
            {"id": str(r.id), "name": r.name, "property_type": r.property_type,
             "wilaya_id": r.wilaya_id,
             "photo_url": r.photos[0] if r.photos else None},
            float(r.latitude), float(r.longitude),
        )
        for r in rows
    ])


@router.get(
    "/experiences.geojson",
    summary="Experiences as GeoJSON",
    description="Active experiences with a meeting point as a GeoJSON FeatureCollection, filtered by wilaya or category.",
    responses={
        422: {"description": "Invalid filter or limit"},
        200: {"description": "GeoJSON FeatureCollection"},
    },
)
async def experiences_geojson(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(1000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
):
    cols = [Experience.id, Experience.title, Experience.category,
            Experience.meeting_point_lat, Experience.meeting_point_lng,
            Experience.photos, Experience.wilaya_id]
    query = select(*cols).where(
        Experience.meeting_point_lat.isnot(None),
        Experience.meeting_point_lng.isnot(None),
        Experience.status == "active",
    )
    if wilaya_id is not None:
        query = query.where(Experience.wilaya_id == wilaya_id)
    if category is not None:
        query = query.where(Experience.category == category)
    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return fc([
        feature(
            {"id": str(r.id), "name": r.title, "category": r.category,
             "wilaya_id": r.wilaya_id,
             "photo_url": r.photos[0] if r.photos else None},
            float(r.meeting_point_lat), float(r.meeting_point_lng),
        )
        for r in rows
    ])


@router.get(
    "/nearby/pois",
    summary="Nearby POIs as GeoJSON",
    description="POIs within a radius (haversine-filtered) returned as a GeoJSON FeatureCollection with distance_km per feature.",
    responses={
        422: {"description": "Invalid lat/lng/radius"},
        200: {"description": "GeoJSON FeatureCollection"},
    },
)
async def nearby_pois(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5, ge=0.1, le=100),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * abs(math.cos(math.radians(lat))) + 0.001)

    cols = [POI.id, POI.name, POI.category, POI.latitude, POI.longitude,
            POI.photo_url, POI.wilaya_id, POI.subtype]
    query = select(*cols).where(
        POI.latitude.isnot(None), POI.longitude.isnot(None),
        POI.latitude.between(lat - lat_delta, lat + lat_delta),
        POI.longitude.between(lng - lng_delta, lng + lng_delta),
    ).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    features = []
    for r in rows:
        d = haversine_km(lat, lng, float(r.latitude), float(r.longitude))
        if d <= radius_km:
            features.append(feature(
                {"id": str(r.id), "name": r.name, "category": r.category,
                 "wilaya_id": r.wilaya_id, "subtype": r.subtype, "distance_km": round(d, 3)},
                float(r.latitude), float(r.longitude),
            ))

    return fc(features)
