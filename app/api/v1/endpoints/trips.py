import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_coordinator_agent,
    get_current_user,
    get_db,
    get_trip_brief_generator,
    get_trip_optimizer,
    get_twilio,
)
from app.core.exceptions import NotFoundException
from app.services.agent.session import ToolContext, set_tool_context
from app.models.poi import POI
from app.models.trip import Trip, TripItem
from app.models.user import User
from app.schemas.trip import (
    DayPlan,
    TripBrief,
    TripCreate,
    TripFeed,
    TripItemCreate,
    TripItemRead,
    TripItemUpdate,
    TripRead,
    TripUpdate,
    TripWhatsAppResponse,
)
from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer
from app.services.twilio import TwilioService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips", tags=["Trip Dashboard"])


async def _build_trip_read(
    db: AsyncSession,
    trip: Trip,
    optimizer: TripOptimizer,
) -> TripRead:
    items = (
        (
            await db.execute(
                select(TripItem)
                .where(TripItem.trip_id == trip.id)
                .order_by(TripItem.day_number, TripItem.sort_order)
            )
        )
        .scalars()
        .all()
    )

    enriched = await optimizer.enrich_items(db, items)

    day_map: dict[int, list[TripItemRead]] = {}
    for e in enriched:
        day_map.setdefault(e.day_number, []).append(e)

    days = []
    total_spent = 0
    for day_num in sorted(day_map):
        day_items = day_map[day_num]
        gaps = await optimizer.detect_gaps(day_items)
        day_total = sum(i.estimated_cost_dzd or 0 for i in day_items)
        total_spent += day_total

        total_km = 0
        for i in range(len(day_items) - 1):
            a, b = day_items[i], day_items[i + 1]
            if a.latitude and a.longitude and b.latitude and b.longitude:
                from app.services.trip_optimizer import Coord, _haversine_km

                total_km += _haversine_km(
                    Coord(a.latitude, a.longitude), Coord(b.latitude, b.longitude)
                )

        days.append(
            DayPlan(
                day_number=day_num,
                items=day_items,
                total_distance_km=round(total_km, 1),
                total_cost_dzd=round(day_total, 0),
                free_slots=gaps,
            )
        )

    budget_remaining = None
    if trip.total_budget_dzd is not None:
        budget_remaining = round(trip.total_budget_dzd - total_spent, 0)

    excluded = {"days", "budget_spent", "budget_remaining"}
    base = TripRead.model_validate(trip).model_dump(exclude=excluded)
    return TripRead(
        **base,
        days=days,
        budget_spent=round(total_spent, 0),
        budget_remaining=budget_remaining,
    )


@router.post("", response_model=TripRead, status_code=201)
async def create_trip(
    body: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = Trip(user_id=current_user.id, **body.model_dump(exclude_none=True))
    db.add(trip)
    await db.commit()
    await db.refresh(trip)

    return await _build_trip_read(db, trip, optimizer)


@router.get("", response_model=TripFeed)
async def list_trips(
    status: str | None = Query(None, pattern="^(active|archived)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    query = select(Trip).where(Trip.user_id == current_user.id)

    if status:
        query = query.where(Trip.status == status)

    query = query.order_by(Trip.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    trips = result.scalars().all()

    items = [await _build_trip_read(db, t, optimizer) for t in trips]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return TripFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/{trip_id}", response_model=TripRead)
async def get_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    return await _build_trip_read(db, trip, optimizer)


@router.put("/{trip_id}", response_model=TripRead)
async def update_trip(
    trip_id: uuid.UUID,
    body: TripUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(trip, field, value)

    await db.commit()
    await db.refresh(trip)

    return await _build_trip_read(db, trip, optimizer)


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    await db.delete(trip)
    await db.commit()


# ── Trip Items ──────────────────────────────────────────────────


@router.post("/{trip_id}/items", response_model=TripRead, status_code=201)
async def add_trip_item(
    trip_id: uuid.UUID,
    body: TripItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    if body.item_type == "poi":
        exists = await db.get(POI, body.item_id)
        if not exists:
            raise NotFoundException(message="POI not found")

    last_item = (
        await db.execute(
            select(TripItem)
            .where(TripItem.trip_id == trip_id, TripItem.day_number == body.day_number)
            .order_by(TripItem.sort_order.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    item = TripItem(
        trip_id=trip_id,
        day_number=body.day_number,
        sort_order=(last_item.sort_order + 1) if last_item else 0,
        time_slot=body.time_slot,
        item_type=body.item_type,
        item_id=body.item_id,
    )
    db.add(item)
    await db.commit()

    return await _build_trip_read(db, trip, optimizer)


@router.put("/{trip_id}/items/{item_id}", response_model=TripRead)
async def update_trip_item(
    trip_id: uuid.UUID,
    item_id: uuid.UUID,
    body: TripItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    item = await db.get(TripItem, item_id)
    if not item or item.trip_id != trip_id:
        raise NotFoundException(message="Trip item not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    await db.commit()

    return await _build_trip_read(db, trip, optimizer)


@router.delete("/{trip_id}/items/{item_id}", response_model=TripRead)
async def delete_trip_item(
    trip_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    item = await db.get(TripItem, item_id)
    if not item or item.trip_id != trip_id:
        raise NotFoundException(message="Trip item not found")

    await db.delete(item)
    await db.commit()

    return await _build_trip_read(db, trip, optimizer)


# ── Optimize ────────────────────────────────────────────────────


@router.post("/{trip_id}/optimize", response_model=TripRead)
async def optimize_trip(
    trip_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
    coordinator: Any = Depends(get_coordinator_agent),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    if coordinator is not None:
        set_tool_context(
            ToolContext(
                db_session=db,
                user_id=str(current_user.id),
                trip_id=str(trip_id),
                locale=getattr(request.state, "locale", "en"),
            )
        )
        try:
            items = (
                (
                    await db.execute(
                        select(TripItem)
                        .where(TripItem.trip_id == trip_id)
                        .order_by(TripItem.day_number, TripItem.sort_order)
                    )
                )
                .scalars()
                .all()
            )
            context = {
                "trip_id": str(trip_id),
                "title": trip.title,
                "items_count": len(items),
            }
            result = await coordinator.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Optimize trip: {context}",
                        }
                    ]
                }
            )
            logger.info("Agent optimization result: %s", result.get("structured_response", {}))
        except Exception as exc:
            logger.warning("Agent optimization failed, falling back: %s", exc)

    items = (
        (
            await db.execute(
                select(TripItem)
                .where(TripItem.trip_id == trip_id)
                .order_by(TripItem.day_number, TripItem.sort_order)
            )
        )
        .scalars()
        .all()
    )

    day_groups: dict[int, list[TripItem]] = {}
    for item in items:
        day_groups.setdefault(item.day_number, []).append(item)

    for _day_num, day_items in day_groups.items():
        sorted_items, _ = await optimizer.optimize_day(db, day_items)
        for i, enriched in enumerate(sorted_items):
            db_item = next((it for it in day_items if it.id == enriched.id), None)
            if db_item:
                db_item.sort_order = i

    await db.commit()

    return await _build_trip_read(db, trip, optimizer)


@router.post("/{trip_id}/optimize/send-whatsapp", response_model=TripWhatsAppResponse)
async def optimize_and_send_whatsapp(
    trip_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    optimizer: TripOptimizer = Depends(get_trip_optimizer),
    twilio: TwilioService = Depends(get_twilio),
):
    trip = await db.get(Trip, trip_id)
    if not trip or trip.user_id != current_user.id:
        raise NotFoundException(message="Trip not found")

    if not twilio.whatsapp_available:
        return TripWhatsAppResponse(sent=False, error="WhatsApp not configured on server")

    if not current_user.phone:
        return TripWhatsAppResponse(sent=False, error="User has no phone number")

    # Run optimization
    items = (
        (
            await db.execute(
                select(TripItem)
                .where(TripItem.trip_id == trip_id)
                .order_by(TripItem.day_number, TripItem.sort_order)
            )
        )
        .scalars()
        .all()
    )

    day_groups: dict[int, list[TripItem]] = {}
    for item in items:
        day_groups.setdefault(item.day_number, []).append(item)

    for _day_num, day_items in day_groups.items():
        sorted_items, _ = await optimizer.optimize_day(db, day_items)
        for i, enriched in enumerate(sorted_items):
            db_item = next((it for it in day_items if it.id == enriched.id), None)
            if db_item:
                db_item.sort_order = i

    await db.commit()

    trip_read = await _build_trip_read(db, trip, optimizer)

    # Format WhatsApp message
    title = trip.title or f"Trip #{str(trip.id)[:8]}"
    lines = [f"\U0001f9ed *{title}*", ""]

    for day in trip_read.days:
        items_str = []
        for item in day.items:
            emoji = "\U0001f4cd" if item.item_type == "poi" else "\u2728"
            cost = f" ({item.estimated_cost_dzd:,.0f} DZD)" if item.estimated_cost_dzd else ""
            items_str.append(f"  {emoji} {item.item_name or 'Unnamed'}{cost}")
        gap_str = f"  \u23f0 Free: {day.free_slots[0]}" if day.free_slots else ""
        lines.append(
            f"\U0001f4c5 *Day {day.day_number}*"
            f" \u2014 {day.total_distance_km} km | {day.total_cost_dzd:,.0f} DZD"
        )
        lines.extend(items_str)
        if gap_str:
            lines.append(gap_str)
        lines.append("")

    budget_line = f"\U0001f4b0 *Budget*: {trip_read.budget_spent:,.0f} DZD spent"
    if trip_read.budget_remaining is not None:
        budget_line += f" | {trip_read.budget_remaining:,.0f} DZD remaining"
    lines.append(budget_line)
    lines.append(f"\U0001f310 {len(trip_read.days)} day(s) planned")

    message = "\n".join(lines)

    sent = await twilio.send_whatsapp(current_user.phone, message)
    return TripWhatsAppResponse(sent=sent, phone=current_user.phone)


# ── Trip Brief ──────────────────────────────────────────────────


@router.get("/brief/{wilaya_id}", response_model=TripBrief)
async def get_trip_brief(
    wilaya_id: int,
    db: AsyncSession = Depends(get_db),
    brief_generator: TripBriefGenerator = Depends(get_trip_brief_generator),
):
    brief = await brief_generator.generate(db, wilaya_id)
    if not brief:
        raise NotFoundException(message="Wilaya not found")

    return brief
