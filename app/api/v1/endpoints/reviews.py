import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.poi import POI
from app.models.review import Review, ReviewVote
from app.models.user import User
from app.schemas.review import (
    OwnerResponseCreate,
    POIRating,
    ReviewCreate,
    ReviewFeed,
    ReviewRead,
    ReviewUpdate,
    ReviewVoteCreate,
    ReviewVoteRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reviews", tags=["Reviews"])


async def _recalc_helpfulness(db: AsyncSession, review_id: uuid.UUID) -> int:
    cnt = await db.scalar(
        select(func.count(ReviewVote.id)).where(
            ReviewVote.review_id == review_id,
            ReviewVote.helpful.is_(True),
        )
    )
    return cnt or 0


async def _build_review_read(review: Review, user_name: str) -> ReviewRead:
    base = ReviewRead.model_validate(review)
    return ReviewRead(
        **base.model_dump(exclude={"user_name", "sub_ratings"}),
        user_name=user_name,
        sub_ratings=review.sub_ratings,
    )


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
        sub_ratings=body.sub_ratings.model_dump() if body.sub_ratings else None,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    return await _build_review_read(
        review,
        current_user.display_name or current_user.phone,
    )


@router.put("/{review_id}", response_model=ReviewRead)
async def update_review(
    review_id: uuid.UUID,
    body: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review:
        raise NotFoundException(message="Review not found")
    if review.user_id != current_user.id:
        raise ForbiddenException(message="You can only edit your own reviews")

    if body.overall_score is not None:
        review.overall_score = body.overall_score
    if body.text is not None:
        review.text = body.text
    if body.sub_ratings is not None:
        review.sub_ratings = body.sub_ratings.model_dump()

    review.edited_at = func.now()
    await db.commit()
    await db.refresh(review)

    user_name = current_user.display_name or current_user.phone
    return await _build_review_read(review, user_name)


@router.get("", response_model=ReviewFeed)
async def list_reviews(
    poi_id: uuid.UUID = Query(...),
    sort: str = Query("recent", pattern="^(recent|highest|lowest|helpful)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="Point of interest not found")

    review_query = (
        select(Review, User.display_name, User.phone)
        .join(User, Review.user_id == User.id)
        .where(Review.poi_id == poi_id)
    )

    if sort == "highest":
        review_query = review_query.order_by(Review.overall_score.desc())
    elif sort == "lowest":
        review_query = review_query.order_by(Review.overall_score)
    elif sort == "helpful":
        review_query = review_query.order_by(Review.helpfulness_count.desc())
    else:
        review_query = review_query.order_by(Review.created_at.desc())

    count_query = select(func.count()).select_from(
        select(Review).where(Review.poi_id == poi_id).subquery()
    )
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(review_query.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for review, display_name, phone in rows:
        items.append(await _build_review_read(review, display_name or phone))

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return ReviewFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
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


@router.post("/{review_id}/vote", response_model=ReviewVoteRead, status_code=201)
async def vote_review(
    review_id: uuid.UUID,
    body: ReviewVoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review:
        raise NotFoundException(message="Review not found")

    if review.user_id == current_user.id:
        raise ForbiddenException(message="Cannot vote on your own review")

    existing = await db.execute(
        select(ReviewVote).where(
            ReviewVote.user_id == current_user.id,
            ReviewVote.review_id == review_id,
        )
    )
    existing_vote = existing.scalar_one_or_none()
    if existing_vote:
        existing_vote.helpful = body.helpful
    else:
        vote = ReviewVote(
            user_id=current_user.id,
            review_id=review_id,
            helpful=body.helpful,
        )
        db.add(vote)

    await db.commit()

    review.helpfulness_count = await _recalc_helpfulness(db, review_id)
    await db.commit()

    vote_result = existing_vote or vote
    await db.refresh(vote_result)
    return ReviewVoteRead.model_validate(vote_result)


@router.post("/{review_id}/respond", response_model=ReviewRead)
async def respond_to_review(
    review_id: uuid.UUID,
    body: OwnerResponseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review:
        raise NotFoundException(message="Review not found")

    poi = await db.get(POI, review.poi_id)
    if not poi:
        raise NotFoundException(message="POI not found")

    if current_user.role != "admin":
        raise ForbiddenException(message="Only admins can respond to reviews")

    review.owner_response = body.response
    review.response_created_at = func.now()
    await db.commit()
    await db.refresh(review)

    user_row = await db.get(User, review.user_id)
    user_name = user_row.display_name or user_row.phone if user_row else "Unknown"
    return await _build_review_read(review, user_name)


@router.delete("/{review_id}", status_code=204)
async def delete_review(
    review_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review:
        raise NotFoundException(message="Review not found")
    if review.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete your own reviews")
    await db.delete(review)
    await db.commit()
