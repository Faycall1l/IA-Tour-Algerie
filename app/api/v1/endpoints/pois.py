import logging
import math
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional, get_db, get_provider_or_admin, get_storage, get_vector_search
from app.core.exceptions import NotFoundException
from app.models.poi import POI
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.poi import POIBrief, POICreate, POIFeed, POIRead, POIUpdate
from app.services.storage import StorageService
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pois", tags=["Points of Interest"])


@router.post("", response_model=POIRead, status_code=201)
async def create_poi(
    body: POICreate,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    wilaya = await db.get(Wilaya, body.wilaya_id)
    if not wilaya:
        raise NotFoundException(message=f"Wilaya {body.wilaya_id} not found")

    poi = POI(**body.model_dump())
    db.add(poi)
    await db.commit()
    await db.refresh(poi)

    vector_search.index_poi(poi)

    return POIRead.model_validate(poi)


@router.post("/{poi_id}/photo", response_model=POIRead)
async def upload_poi_photo(
    poi_id: uuid.UUID,
    photo: UploadFile = File(...),
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    photo_url = await storage.upload(photo, folder="pois")
    poi.photo_url = photo_url
    await db.commit()
    await db.refresh(poi)
    return POIRead.model_validate(poi)


@router.get("/neighborhoods", response_model=list[str])
async def list_neighborhoods(
    wilaya_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(POI.neighborhood).where(
        POI.neighborhood.isnot(None),
        POI.neighborhood != "",
    ).distinct().order_by(POI.neighborhood)

    if wilaya_id:
        query = query.where(POI.wilaya_id == wilaya_id)

    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("", response_model=POIFeed)
async def list_pois(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
    neighborhood: str | None = Query(None),
    search: str | None = Query(None),
    sort: str | None = Query(None, pattern="^(name|created_at|rating)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(POI)

    if sort == "created_at":
        query = query.order_by(POI.created_at.desc())
    elif sort == "name":
        query = query.order_by(POI.name)
    else:
        query = query.order_by(POI.name)

    if wilaya_id:
        query = query.where(POI.wilaya_id == wilaya_id)
    if category:
        query = query.where(POI.category == category)
    if neighborhood:
        query = query.where(POI.neighborhood.ilike(f"%{neighborhood}%"))
    if search:
        query = query.where(POI.name.ilike(f"%{search}%") | (POI.description.ilike(f"%{search}%")))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    pois = list(result.scalars().all())

    items = [POIRead.model_validate(p) for p in pois]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return POIFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/nearby", response_model=list[POIBrief])
async def nearby_pois(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5, ge=0.1, le=100),
    limit: int = Query(20, ge=1, le=50),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from app.models.poi import POI

    deg = radius_km / 111.0
    query = select(
        POI.id, POI.name, POI.category, POI.subtype,
        POI.wilaya_id, POI.latitude, POI.longitude,
        POI.photo_url, POI.is_featured,
    ).where(
        POI.latitude.isnot(None),
        POI.longitude.isnot(None),
        POI.latitude.between(lat - deg, lat + deg),
        POI.longitude.between(lng - deg, lng + deg),
    )
    if category:
        query = query.where(POI.category == category)

    result = await db.execute(query)
    rows = result.all()

    def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    items = []
    for r in rows:
        dist = _haversine_km(lat, lng, float(r.latitude), float(r.longitude))
        if dist <= radius_km:
            items.append((dist, r))

    items.sort(key=lambda x: x[0])
    return [
        POIBrief(
            id=r.id, name=r.name, category=r.category, subtype=r.subtype,
            wilaya_id=r.wilaya_id, latitude=float(r.latitude) if r.latitude else None,
            longitude=float(r.longitude) if r.longitude else None,
            photo_url=r.photo_url, is_featured=r.is_featured,
            distance_km=round(dist, 2),
        )
        for dist, r in items[:limit]
    ]


@router.get("/search", response_model=POIFeed)
async def search_pois(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    ids = vector_search.search(q, limit=limit)
    pois: list[POI] = []
    if ids:
        seen = set()
        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            poi = await db.get(POI, pid)
            if poi:
                pois.append(poi)

    # SQL full-text search fallback when Qdrant returns nothing or is unavailable
    if not pois:
        tsq = func.plainto_tsquery("french", q)
        stmt = (
            select(POI)
            .where(POI.search_vector.op("@@")(tsq))
            .order_by(func.ts_rank(POI.search_vector, tsq).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        pois = list(result.scalars().all())

    items = [POIRead.model_validate(p) for p in pois]
    total = len(items)
    return POIFeed(
        items=items,
        total=total,
        page=1,
        page_size=total or 1,
        total_pages=1,
        has_prev=False,
        has_next=False,
    )


@router.get("/{poi_id}", response_model=POIRead)
async def get_poi(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    result = POIRead.model_validate(poi)

    if current_user:
        from app.models.favorite import Favorite
        fav = await db.execute(
            select(Favorite).where(
                Favorite.user_id == current_user.id,
                Favorite.entity_type == "poi",
                Favorite.entity_id == poi_id,
            )
        )
        result.is_favorited = fav.scalar_one_or_none() is not None

    return result


@router.patch("/{poi_id}", response_model=POIRead)
async def update_poi(
    poi_id: uuid.UUID,
    body: POIUpdate,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return POIRead.model_validate(poi)

    for field, value in updates.items():
        setattr(poi, field, value)

    await db.commit()
    await db.refresh(poi)
    vector_search.index_poi(poi)

    return POIRead.model_validate(poi)


@router.get("/{poi_id}/similar", response_model=list[POIBrief])
async def similar_pois(
    poi_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    cols = [
        POI.id, POI.name, POI.category, POI.subtype, POI.wilaya_id,
        POI.latitude, POI.longitude, POI.photo_url, POI.is_featured,
    ]
    # Same category + wilaya first, same wilaya only second
    query = select(*cols).where(
        POI.id != poi_id,
        POI.latitude.isnot(None),
        POI.longitude.isnot(None),
        POI.category.in_([poi.category, "other"]),
        POI.wilaya_id == poi.wilaya_id,
    ).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    if len(rows) < limit:
        existing_ids = [r[0] for r in rows] + [poi_id]
        query2 = select(*cols).where(
            POI.id.notin_(existing_ids),
            POI.wilaya_id == poi.wilaya_id,
        ).limit(limit - len(rows))
        result2 = await db.execute(query2)
        rows.extend(result2.all())

    return [
        POIBrief(
            id=r[0], name=r[1], category=r[2], subtype=r[3],
            wilaya_id=r[4], latitude=float(r[5]) if r[5] else None,
            longitude=float(r[6]) if r[6] else None,
            photo_url=r[7], is_featured=r[8],
        )
        for r in rows
    ]


@router.delete("/{poi_id}", status_code=204)
async def delete_poi(
    poi_id: uuid.UUID,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")
    await db.delete(poi)
    await db.commit()
    vector_search.delete_poi(poi_id)


@router.get("/tour/optimize")
async def optimize_poi_tour(
    wilaya_id: int = Query(..., ge=1, le=69),
    budget_hours: float = Query(8.0, ge=1.0, le=16.0),
    categories: str | None = Query(None, description="Comma-separated categories"),
    max_pois: int = Query(15, ge=3, le=30),
    start_poi_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    from app.services.poi_graph import POIGraphService

    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    service = POIGraphService()
    result = await service.optimize_tour(
        db, wilaya_id, budget_hours, cat_list, max_pois, start_poi_id,
    )
    if not result:
        return {"message": "No POIs found for this wilaya", "stops": []}

    return {
        "wilaya_id": result.wilaya_id,
        "budget_hours": result.budget_hours,
        "total_pois": result.total_pois,
        "total_walk_min": result.total_walk_min,
        "total_visit_min": result.total_visit_min,
        "total_time_min": result.total_time_min,
        "walking_distance_km": result.walking_distance_km,
        "stops": [
            {
                "poi_id": s.poi_id,
                "poi_name": s.poi_name,
                "category": s.category,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "duration_min": s.duration_min,
                "walk_from_prev_min": s.walk_from_prev_min,
                "cumulative_time_min": s.cumulative_time_min,
                "fun_fact": s.fun_fact,
            }
            for s in result.stops
        ],
    }


@router.get("/tour/clusters")
async def poi_clusters(
    wilaya_id: int = Query(..., ge=1, le=69),
    radius_m: float = Query(1000.0, ge=200.0, le=5000.0),
    db: AsyncSession = Depends(get_db),
):
    from app.services.poi_graph import POIGraphService

    service = POIGraphService()
    clusters = await service.cluster_pois(db, wilaya_id, radius_m)
    return {
        "wilaya_id": wilaya_id,
        "radius_m": radius_m,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "poi_count": len(c.pois),
                "center_lat": round(c.center_lat, 4),
                "center_lon": round(c.center_lon, 4),
                "radius_m": round(c.radius_m, 0),
                "walkable": c.walkable,
                "pois": [
                    {"id": p.id, "name": p.name, "category": p.category}
                    for p in c.pois[:5]
                ],
            }
            for c in clusters[:10]
        ],
    }


@router.get("/tour/hubs")
async def hub_pois(
    wilaya_id: int = Query(..., ge=1, le=69),
    top_n: int = Query(10, ge=3, le=30),
    db: AsyncSession = Depends(get_db),
):
    from app.services.poi_graph import POIGraphService

    service = POIGraphService()
    hubs = await service.hub_pois(db, wilaya_id, top_n)
    return {"wilaya_id": wilaya_id, "hub_pois": hubs}
