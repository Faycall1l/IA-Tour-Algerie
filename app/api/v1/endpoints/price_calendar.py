import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.experience import Experience
from app.models.experience_price import ExperiencePrice
from app.models.user import User
from app.schemas.experience_price import (
    ExperiencePriceBatchCreate,
    ExperiencePriceCalendar,
    ExperiencePriceCreate,
    ExperiencePriceRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/price-calendar", tags=["Price Calendar"])


async def _build_price_read(ep: ExperiencePrice) -> ExperiencePriceRead:
    return ExperiencePriceRead(
        id=ep.id,
        experience_id=ep.experience_id,
        date=ep.date,
        price_dzd=ep.price_dzd,
        available_spots=ep.available_spots,
    )


@router.get("/experiences/{experience_id}", response_model=ExperiencePriceCalendar)
async def get_experience_calendar(
    experience_id: uuid.UUID,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    exp = await db.get(Experience, experience_id)
    if not exp:
        raise NotFoundException(message="Experience not found")

    query = select(ExperiencePrice).where(ExperiencePrice.experience_id == experience_id)

    if from_date:
        query = query.where(ExperiencePrice.date >= from_date)
    if to_date:
        query = query.where(ExperiencePrice.date <= to_date)

    query = query.order_by(ExperiencePrice.date)
    result = await db.execute(query)
    prices_raw = result.scalars().all()

    prices = [await _build_price_read(p) for p in prices_raw]

    if not prices:
        return ExperiencePriceCalendar(
            experience_id=experience_id,
            prices=[],
            min_price=0,
            max_price=0,
            available_dates=0,
        )

    min_price = min(p.price_dzd for p in prices)
    max_price = max(p.price_dzd for p in prices)

    return ExperiencePriceCalendar(
        experience_id=experience_id,
        prices=prices,
        min_price=min_price,
        max_price=max_price,
        available_dates=len(prices),
    )


@router.post("/experiences/{experience_id}", response_model=list[ExperiencePriceRead], status_code=201)
async def set_experience_prices(
    experience_id: uuid.UUID,
    body: ExperiencePriceBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exp = await db.get(Experience, experience_id)
    if not exp:
        raise NotFoundException(message="Experience not found")
    if exp.provider_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only set prices for your own experiences")

    if not body.prices:
        raise BadRequestException(message="At least one price entry required")

    created = []
    for entry in body.prices:
        if entry.date < date.today():
            raise BadRequestException(message=f"Date {entry.date} is in the past")
        ep = ExperiencePrice(
            experience_id=experience_id,
            date=entry.date,
            price_dzd=entry.price_dzd,
            available_spots=entry.available_spots,
        )
        db.add(ep)
        created.append(ep)

    await db.commit()
    for ep in created:
        await db.refresh(ep)

    return [await _build_price_read(ep) for ep in created]


@router.delete("/{price_id}", status_code=204)
async def delete_price(
    price_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ep = await db.get(ExperiencePrice, price_id)
    if not ep:
        raise NotFoundException(message="Price entry not found")

    exp = await db.get(Experience, ep.experience_id)
    if exp and exp.provider_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete prices for your own experiences")

    await db.delete(ep)
    await db.commit()
