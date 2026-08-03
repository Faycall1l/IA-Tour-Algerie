import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.recommendation import (
    PreferenceRead,
    PreferenceUpdate,
    RecommendationFeed,
    RecommendationFeedback,
    RecommendationRead,
)
from app.services.recommendation import recommendation_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get(
    "",
    response_model=RecommendationFeed,
    summary="Get recommendations",
    description="Personalized content-based recommendations (model cbf_v1) for the authenticated user, filtered by wilaya and entity type.",
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Invalid filter"},
    },
)
async def get_recommendations(
    wilaya_id: int | None = Query(None, ge=1, le=58),
    entity_type: str | None = Query(None, pattern="^(poi|experience|stay)$"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    recs = await recommendation_engine.generate_recommendations(
        db, current_user.id, wilaya_id=wilaya_id, entity_type=entity_type, limit=limit,
    )
    items = [RecommendationRead.model_validate(r) for r in recs]
    return RecommendationFeed(items=items, total=len(items), model_version="cbf_v1")


@router.get(
    "/preferences",
    response_model=PreferenceRead,
    summary="Get preferences",
    description="The user's inferred travel preferences (categories, budgets). Auto-creates a default profile on first access.",
    responses={401: {"description": "Authentication required"}},
)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await recommendation_engine.get_or_create_preferences(db, current_user.id)
    return PreferenceRead.model_validate(pref)


@router.patch(
    "/preferences",
    response_model=PreferenceRead,
    summary="Update preferences",
    description="Partially update the user's travel preferences.",
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Validation error"},
    },
)
async def update_preferences(
    body: PreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await recommendation_engine.get_or_create_preferences(db, current_user.id)
    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(pref, k, v)
    await db.flush()
    await db.refresh(pref)
    return PreferenceRead.model_validate(pref)


@router.post(
    "/preferences/derive",
    response_model=PreferenceRead,
    summary="Re-derive preferences",
    description="Rebuild the user's preferences from their interaction history (favorites, collections, trips).",
    responses={401: {"description": "Authentication required"}},
)
async def derive_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await recommendation_engine.update_preferences_from_interactions(db, current_user.id)
    return PreferenceRead.model_validate(pref)


@router.post(
    "/{rec_id}/feedback",
    response_model=RecommendationRead,
    summary="Submit recommendation feedback",
    description="Record feedback on a recommendation: liked, dismissed, or bookmarked. Dismissed hides it; liked/bookmarked marks it seen.",
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Recommendation not found"},
    },
)
async def submit_feedback(
    rec_id: uuid.UUID,
    body: RecommendationFeedback,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(Recommendation, rec_id)
    if not rec or rec.user_id != current_user.id:
        raise NotFoundException(message="Recommendation not found")

    rec.feedback = body.feedback
    if body.feedback == "dismissed":
        rec.is_dismissed = True
    elif body.feedback in ("liked", "bookmarked"):
        rec.is_seen = True
    await db.flush()
    return RecommendationRead.model_validate(rec)
