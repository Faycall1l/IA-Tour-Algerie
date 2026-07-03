import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.poi import POI
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.poi import POICreate, POIFeed, POIRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pois", tags=["Points of Interest"])


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


@router.get("", response_model=POIFeed)
async def list_pois(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(POI).order_by(POI.name)

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
    pois = result.scalars().all()

    return POIFeed(
        items=[POIRead.model_validate(p) for p in pois],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{poi_id}", response_model=POIRead)
async def get_poi(poi_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")
    return POIRead.model_validate(poi)
