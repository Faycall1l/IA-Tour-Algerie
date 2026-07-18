import logging
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user, get_db, get_storage, get_vector_search
from app.core.exceptions import NotFoundException
from app.models.poi import POI
from app.models.review import Review
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.poi import POIBrief, POICreate, POIFeed, POIRead, POIUpdate, TopReview
from app.services.storage import StorageService
from app.services.vector_search import VectorSearchService

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

    top_reviews_query = (
        select(Review, User.display_name, User.phone)
        .join(User, Review.user_id == User.id)
        .where(Review.poi_id.in_(poi_ids))
        .order_by(Review.helpfulness_count.desc(), Review.created_at.desc())
    )
    top_rows = (await db.execute(top_reviews_query)).all()
    top_map: dict[uuid.UUID, list[TopReview]] = {}
    for review, display_name, phone in top_rows:
        name = display_name or phone
        tr = TopReview(
            id=review.id,
            user_name=name,
            overall_score=review.overall_score,
            text=review.text,
            created_at=review.created_at,
            helpfulness_count=review.helpfulness_count,
        )
        top_map.setdefault(review.poi_id, []).append(tr)

    items = []
    for p in pois:
        avg, cnt = ratings_map.get(p.id, (None, 0))
        base = POIRead.model_validate(p)
        base.average_score = avg
        base.total_reviews = cnt
        base.top_reviews = (top_map.get(p.id) or [])[:3]
        items.append(base)
    return items


@router.post("", response_model=POIRead, status_code=201)
async def create_poi(
    body: POICreate,
    _current_user: User = Depends(get_current_user),
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

    items = await _attach_ratings(db, pois)

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
        from sqlalchemy import func
        from app.models.poi import POI

        tsq = func.plainto_tsquery("french", q)
        stmt = (
            select(POI)
            .where(POI.search_vector.op("@@")(tsq))
            .order_by(func.ts_rank(POI.search_vector, tsq).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        pois = list(result.scalars().all())

    items = await _attach_ratings(db, pois)
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
async def get_poi(poi_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    items = await _attach_ratings(db, [poi])
    return items[0]


@router.patch("/{poi_id}", response_model=POIRead)
async def update_poi(
    poi_id: uuid.UUID,
    body: POIUpdate,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        items = await _attach_ratings(db, [poi])
        return items[0]

    for field, value in updates.items():
        setattr(poi, field, value)

    await db.commit()
    await db.refresh(poi)
    vector_search.index_poi(poi)

    items = await _attach_ratings(db, [poi])
    return items[0]


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
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")
    await db.delete(poi)
    await db.commit()
    vector_search.delete_poi(poi_id)
