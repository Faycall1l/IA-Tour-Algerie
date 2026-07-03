import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ConflictException, NotFoundException
from app.models.poi import POI
from app.models.review import Review
from app.models.user import User
from app.schemas.review import POIRating, ReviewCreate, ReviewFeed, ReviewRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.post("", response_model=ReviewRead, status_code=201)
async def create_review(
    body: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    poi = await db.get(POI, body.poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    existing = await db.execute(
        select(Review).where(
            Review.user_id == current_user.id,
            Review.poi_id == body.poi_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException(message="You already reviewed this POI")

    review = Review(
        user_id=current_user.id,
        poi_id=body.poi_id,
        overall_score=body.overall_score,
        text=body.text,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    return ReviewRead.model_validate(review)


@router.get("", response_model=ReviewFeed)
async def list_reviews(
    poi_id: uuid.UUID = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    query = select(Review).where(Review.poi_id == poi_id).order_by(Review.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    reviews = result.scalars().all()

    return ReviewFeed(
        items=[ReviewRead.model_validate(r) for r in reviews],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/ratings/{poi_id}", response_model=POIRating)
async def get_poi_ratings(poi_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    scores = await db.execute(select(Review.overall_score).where(Review.poi_id == poi_id))
    all_scores = [row[0] for row in scores.all()]

    if not all_scores:
        return POIRating(
            poi_id=poi_id,
            average_score=0.0,
            total_reviews=0,
            distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        )

    distribution: dict[int, int] = defaultdict(int)
    for s in all_scores:
        distribution[int(s)] += 1

    return POIRating(
        poi_id=poi_id,
        average_score=round(sum(all_scores) / len(all_scores), 1),
        total_reviews=len(all_scores),
        distribution=dict(sorted(distribution.items())),
    )
