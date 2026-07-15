import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.experience import Experience
from app.models.price_calendar_entry import PriceCalendarEntry
from app.models.stay import Stay
from app.models.user import User
from app.schemas.price_calendar import (
    PriceCalendarBatchCreate,
    PriceCalendarEntryCreate,
    PriceCalendarEntryRead,
    PriceCalendarRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/price-calendar", tags=["Price Calendar"])


async def _build_entry_read(entry: PriceCalendarEntry) -> PriceCalendarEntryRead:
    return PriceCalendarEntryRead(
        id=entry.id,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        date=entry.date,
        price_dzd=entry.price_dzd,
        available_spots=entry.available_spots,
    )


ENTITY_MODEL_MAP = {
    "experience": Experience,
    "stay": Stay,
}


async def _resolve_entity(entity_type: str, entity_id: uuid.UUID, db: AsyncSession):
    model = ENTITY_MODEL_MAP.get(entity_type)
    if not model:
        raise BadRequestException(message=f"Invalid entity_type '{entity_type}'. Must be 'experience' or 'stay'")
    obj = await db.get(model, entity_id)
    if not obj:
        raise NotFoundException(message=f"{entity_type.title()} not found")
    return obj


async def _check_ownership(entity_type: str, obj, current_user: User):
    if entity_type == "experience":
        if obj.provider_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException(message="You can only set prices for your own experiences")
    elif entity_type == "stay":
        if obj.provider_id != current_user.id and current_user.role != "admin":
            raise ForbiddenException(message="You can only set prices for your own stays")


@router.get("/{entity_type}/{entity_id}", response_model=PriceCalendarRead)
async def get_price_calendar(
    entity_type: str,
    entity_id: uuid.UUID,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    await _resolve_entity(entity_type, entity_id, db)

    query = select(PriceCalendarEntry).where(
        PriceCalendarEntry.entity_type == entity_type,
        PriceCalendarEntry.entity_id == entity_id,
    )

    if from_date:
        query = query.where(PriceCalendarEntry.date >= from_date)
    if to_date:
        query = query.where(PriceCalendarEntry.date <= to_date)

    query = query.order_by(PriceCalendarEntry.date)
    result = await db.execute(query)
    entries_raw = result.scalars().all()

    entries = [await _build_entry_read(e) for e in entries_raw]

    if not entries:
        return PriceCalendarRead(
            entity_id=entity_id,
            entity_type=entity_type,
            prices=[],
            min_price=0,
            max_price=0,
            available_dates=0,
        )

    min_price = min(e.price_dzd for e in entries)
    max_price = max(e.price_dzd for e in entries)

    return PriceCalendarRead(
        entity_id=entity_id,
        entity_type=entity_type,
        prices=entries,
        min_price=min_price,
        max_price=max_price,
        available_dates=len(entries),
    )


@router.post("/{entity_type}/{entity_id}", response_model=list[PriceCalendarEntryRead], status_code=201)
async def set_price_calendar(
    entity_type: str,
    entity_id: uuid.UUID,
    body: PriceCalendarBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await _resolve_entity(entity_type, entity_id, db)
    await _check_ownership(entity_type, obj, current_user)

    if not body.prices:
        raise BadRequestException(message="At least one price entry required")

    created = []
    for entry in body.prices:
        if entry.date < date.today():
            raise BadRequestException(message=f"Date {entry.date} is in the past")
        pc = PriceCalendarEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            date=entry.date,
            price_dzd=entry.price_dzd,
            available_spots=entry.available_spots,
        )
        db.add(pc)
        created.append(pc)

    await db.commit()
    for pc in created:
        await db.refresh(pc)

    return [await _build_entry_read(pc) for pc in created]


@router.delete("/{price_id}", status_code=204)
async def delete_price_entry(
    price_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(PriceCalendarEntry, price_id)
    if not entry:
        raise NotFoundException(message="Price entry not found")

    obj = await _resolve_entity(entry.entity_type, entry.entity_id, db)
    await _check_ownership(entry.entity_type, obj, current_user)

    await db.delete(entry)
    await db.commit()
