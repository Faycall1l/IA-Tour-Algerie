import logging
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage
from app.core.exceptions import NotFoundException
from app.models.poi import POI
from app.models.review import Review
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.poi import POICreate, POIFeed, POIRead
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pois", tags=["Points of Interest"])


async def _attach_ratings(db: AsyncSession, pois: list[POI]) -> list[POIRead]:
    if not pois:
        return []

    poi_ids = [p.id for p in pois]
    ratings_query = (
        select(
            Review.poi_id,
            func.avg(Review.overall_score).label("avg"),
            func.count(Review.id).label("cnt"),
        )
        .where(Review.poi_id.in_(poi_ids))
        .group_by(Review.poi_id)
    )
    ratings_map: dict[uuid.UUID, tuple[float, int]] = {}
    for row in await db.execute(ratings_query):
        ratings_map[row.poi_id] = (round(float(row.avg), 1), row.cnt)

    items = []
    for p in pois:
        avg, cnt = ratings_map.get(p.id, (None, 0))
        base = POIRead.model_validate(p)
        items.append(POIRead(**base.model_dump(), average_score=avg, total_reviews=cnt))
    return items


@router.post("", response_model=POIRead, status_code=201)
async def create_poi(
    body: POICreate,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wilaya = await db.get(Wilaya, body.wilaya_id)
    if not wilaya:
        raise NotFoundException(message=f"Wilaya {body.wilaya_id} not found")

    poi = POI(**body.model_dump())
    db.add(poi)
    await db.commit()
    await db.refresh(poi)

    return POIRead.model_validate(poi)


@router.post("/{poi_id}/photo", response_model=POIRead)
async def upload_poi_photo(
    poi_id: uuid.UUID,
    photo: UploadFile = File(...),
    _current_user: User = Depends(get_current_user),
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
    items = await _attach_ratings(db, [poi])
    return items[0]


@router.get("", response_model=POIFeed)
async def list_pois(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
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
    if search:
        query = query.where(POI.name.ilike(f"%{search}%") | (POI.description.ilike(f"%{search}%")))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    pois = list(result.scalars().all())

    items = await _attach_ratings(db, pois)

    return POIFeed(items=items, total=total, page=page, page_size=page_size)


@router.get("/{poi_id}", response_model=POIRead)
async def get_poi(poi_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    items = await _attach_ratings(db, [poi])
    return items[0]
