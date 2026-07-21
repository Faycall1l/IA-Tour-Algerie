"""User-contributed data suggestions for POIs, stays, and experiences.

Users can suggest edits to phone, website, opening_hours, description, etc.
Admins review and approve/reject. This is the crowdsourced data improvement pipeline.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.experience import Experience
from app.models.poi import POI
from app.models.suggestion import SUGGESTION_FIELDS, Suggestion
from app.models.stay import Stay
from app.models.user import User
from app.schemas.suggestion import SuggestionCreate, SuggestionFeed, SuggestionRead, SuggestionReview

router = APIRouter(prefix="/suggestions", tags=["Suggestions"])

ENTITY_MODELS = {
    "poi": POI,
    "stay": Stay,
    "experience": Experience,
}


@router.post("", response_model=SuggestionRead, status_code=201)
async def create_suggestion(
    body: SuggestionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify entity exists
    model = ENTITY_MODELS.get(body.entity_type)
    if not model:
        raise BadRequestException(message=f"Unknown entity type: {body.entity_type}")
    entity = await db.get(model, body.entity_id)
    if not entity:
        raise NotFoundException(message=f"{body.entity_type} not found")

    # Get current value
    old_value = getattr(entity, body.field_name, None)
    if old_value and isinstance(old_value, str):
        old_value = old_value
    elif old_value is not None:
        old_value = str(old_value)

    suggestion = Suggestion(
        user_id=current_user.id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        field_name=body.field_name,
        old_value=old_value,
        new_value=body.new_value,
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionRead.model_validate(suggestion)


@router.get("", response_model=SuggestionFeed)
async def list_suggestions(
    status: str | None = Query(None, pattern="^(pending|approved|rejected)$"),
    entity_type: str | None = Query(None, pattern="^(poi|stay|experience)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        query = select(Suggestion).where(Suggestion.user_id == current_user.id)
    else:
        query = select(Suggestion)

    if status:
        query = query.where(Suggestion.status == status)
    if entity_type:
        query = query.where(Suggestion.entity_type == entity_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Suggestion.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [SuggestionRead.model_validate(s) for s in result.scalars().all()]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return SuggestionFeed(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{suggestion_id}/review", response_model=SuggestionRead)
async def review_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionReview,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise ForbiddenException(message="Only admins can review suggestions")

    suggestion = await db.get(Suggestion, suggestion_id)
    if not suggestion:
        raise NotFoundException(message="Suggestion not found")
    if suggestion.status != "pending":
        raise BadRequestException(message="Suggestion already reviewed")

    suggestion.status = body.status
    suggestion.reviewed_by = current_user.id
    suggestion.review_notes = body.review_notes

    # Auto-apply approved suggestions
    if body.status == "approved":
        model = ENTITY_MODELS.get(suggestion.entity_type)
        if model:
            await db.execute(
                update(model)
                .where(model.id == suggestion.entity_id)
                .values({suggestion.field_name: suggestion.new_value})
            )

    await db.commit()
    await db.refresh(suggestion)
    return SuggestionRead.model_validate(suggestion)
