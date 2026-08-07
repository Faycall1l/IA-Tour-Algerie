import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_provider_or_admin
from app.core.exceptions import NotFoundException
from app.models.event import Event
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.event import EventCreate, EventFeed, EventRead, EventUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "",
    response_model=EventFeed,
    summary="List events",
    description="Paginated events/festivals calendar filtered by wilaya, category, and month (1-12). Public.",  # noqa: E501
    responses={422: {"description": "Validation error"}},
)
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


@router.get(
    "/{event_id}",
    response_model=EventRead,
    summary="Get an event",
    description="Event detail. Public.",
    responses={
        404: {"description": "Event not found"},
        422: {"description": "Invalid UUID"},
    },
)
async def get_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundException(message="Event not found")
    return EventRead.model_validate(event)


@router.post(
    "",
    response_model=EventRead,
    status_code=201,
    summary="Create an event",
    description="Add an event/festival to the calendar. Requires provider or admin role; the wilaya must exist.",  # noqa: E501
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Provider or admin role required"},
        404: {"description": "Wilaya not found"},
        422: {"description": "Validation error"},
    },
)
async def create_event(
    body: EventCreate,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
):
    wilaya = await db.get(Wilaya, body.wilaya_id)
    if not wilaya:
        raise NotFoundException(message=f"Wilaya {body.wilaya_id} not found")

    event = Event(**body.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventRead.model_validate(event)


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    summary="Update an event",
    description="Partial update of an event (provider or admin role).",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Provider or admin role required"},
        404: {"description": "Event not found"},
    },
)
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdate,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundException(message="Event not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return EventRead.model_validate(event)

    for field, value in updates.items():
        setattr(event, field, value)

    await db.commit()
    await db.refresh(event)
    return EventRead.model_validate(event)


@router.delete(
    "/{event_id}",
    status_code=204,
    summary="Delete an event",
    description="Delete an event (provider or admin role).",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Provider or admin role required"},
        404: {"description": "Event not found"},
    },
)
async def delete_event(
    event_id: uuid.UUID,
    _current_user: User = Depends(get_provider_or_admin),
    db: AsyncSession = Depends(get_db),
):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundException(message="Event not found")
    await db.delete(event)
    await db.commit()
