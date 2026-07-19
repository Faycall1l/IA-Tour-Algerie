import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.models.visit import Visit
from app.schemas.visit import VisitCreate, VisitFeed, VisitRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/visits", tags=["Visits"])


@router.post("", response_model=VisitRead, status_code=201)
async def check_in(
    body: VisitCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Visit).where(
            Visit.user_id == current_user.id,
            Visit.entity_type == body.entity_type,
            Visit.entity_id == body.entity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise NotFoundException(message="Already checked in")

    visit = Visit(user_id=current_user.id, entity_type=body.entity_type, entity_id=body.entity_id)
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return VisitRead.model_validate(visit)


@router.get("", response_model=VisitFeed)
async def list_visits(
    entity_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Visit).where(Visit.user_id == current_user.id)
    if entity_type:
        query = query.where(Visit.entity_type == entity_type)
    query = query.order_by(Visit.visited_at.desc())

    result = await db.execute(query)
    items = [VisitRead.model_validate(v) for v in result.scalars().all()]
    return VisitFeed(items=items, total=len(items))


@router.delete("/{visit_id}", status_code=204)
async def remove_visit(
    visit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    visit = await db.get(Visit, visit_id)
    if not visit or visit.user_id != current_user.id:
        raise NotFoundException(message="Visit not found")
    await db.delete(visit)
    await db.commit()


@router.get("/count", response_model=int)
async def visit_count(
    entity_type: str,
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.entity_type == entity_type,
            Visit.entity_id == entity_id,
        )
    )
    return result.scalar() or 0
