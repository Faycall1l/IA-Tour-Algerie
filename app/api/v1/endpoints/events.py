import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundException
from app.models.event import Event
from app.schemas.event import EventFeed, EventRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=EventFeed)
async def list_events(
    wilaya_id: int | None = Query(None, ge=1, le=58),
    category: str | None = Query(None, max_length=50),
    month: int | None = Query(None, ge=1, le=12),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Event)

    if wilaya_id:
        query = query.where(Event.wilaya_id == wilaya_id)
    if category:
        query = query.where(Event.category == category)
    if month:
        query = query.where(Event.month == month)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Event.month, Event.title).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [EventRead.model_validate(e) for e in result.scalars().all()]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return EventFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID

    event = await db.get(Event, UUID(event_id))
    if not event:
        raise NotFoundException(message="Event not found")
    return EventRead.model_validate(event)
