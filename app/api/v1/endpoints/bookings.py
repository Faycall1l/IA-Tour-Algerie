"""Polymorphic bookings supporting experiences AND circuits.

entity_type = 'experience' | 'circuit'
entity_id   = UUID of the experience or circuit
"""

import logging
import uuid
from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.booking import BOOKING_STATUSES, Booking
from app.models.circuit import Circuit
from app.models.experience import Experience
from app.models.notification import Notification
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingDetail, BookingRead, BookingStatusUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["Bookings"])


async def _notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    type: str,
    title: str,
    message: str | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
) -> None:
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    db.add(notif)


async def _resolve_entity(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> tuple:
    """Resolve an entity to (entity_obj, provider_id, title)."""
    if entity_type == "experience":
        obj = await db.get(Experience, entity_id)
        if not obj:
            raise NotFoundException(message="Experience not found")
        if obj.status != "active":
            raise BadRequestException(message="Experience is not available")
        return obj, obj.provider_id, obj.title
    elif entity_type == "circuit":
        obj = await db.get(Circuit, entity_id)
        if not obj or not obj.is_active:
            raise NotFoundException(message="Circuit not found")
        return obj, None, obj.title
    raise BadRequestException(message=f"Unknown entity type: {entity_type}")


@router.post("", response_model=BookingDetail, status_code=201)
async def create_booking(
    body: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity, provider_id, title = await _resolve_entity(db, body.entity_type, body.entity_id)

    if provider_id and provider_id == current_user.id:
        raise BadRequestException(message="You cannot book your own entity")

    booking = Booking(
        traveler_id=current_user.id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        message=body.message,
        participants=body.participants,
        requested_date=body.requested_date,
    )
    db.add(booking)
    await db.flush()

    if provider_id:
        await _notify(
            db,
            user_id=provider_id,
            type="booking_request",
            title="New booking request",
            message=f"{current_user.display_name or current_user.phone} wants to join '{title}'",
            reference_type="booking",
            reference_id=booking.id,
        )
    await db.commit()
    await db.refresh(booking)

    provider = await db.get(User, provider_id) if provider_id else None
    return BookingDetail(
        booking=BookingRead.model_validate(booking),
        traveler_name=current_user.display_name or current_user.phone,
        traveler_avatar=current_user.avatar_url,
        booking_title=title,
        provider_id=provider_id,
        provider_name=provider.display_name or provider.phone if provider else None,
    )


@router.get("", response_model=list[BookingDetail])
async def list_bookings(
    status: str | None = Query(None, pattern=f"^({'|'.join(BOOKING_STATUSES)})$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Booking).where(
        or_(
            Booking.traveler_id == current_user.id,
            Booking.entity_id.in_(
                select(Experience.id).where(Experience.provider_id == current_user.id)
            ),
        )
    )
    if status:
        query = query.where(Booking.status == status)
    query = query.order_by(Booking.created_at.desc())
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    bookings = result.scalars().all()

    items = []
    for b in bookings:
        traveler = await db.get(User, b.traveler_id)
        title = None
        pid = None
        try:
            _, pid, title = await _resolve_entity(db, b.entity_type, b.entity_id)
        except Exception:
            pass
        provider = await db.get(User, pid) if pid else None
        items.append(
            BookingDetail(
                booking=BookingRead.model_validate(b),
                traveler_name=traveler.display_name or traveler.phone if traveler else None,
                traveler_avatar=traveler.avatar_url if traveler else None,
                booking_title=title,
                provider_id=pid,
                provider_name=provider.display_name or provider.phone if provider else None,
            )
        )
    return items


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise NotFoundException(message="Booking not found")

    entity, provider_id, title = await _resolve_entity(db, booking.entity_type, booking.entity_id)
    if booking.traveler_id != current_user.id and (
        not provider_id or provider_id != current_user.id
    ):
        raise ForbiddenException(message="You cannot view this booking")

    traveler = await db.get(User, booking.traveler_id)
    provider = await db.get(User, provider_id) if provider_id else None
    return BookingDetail(
        booking=BookingRead.model_validate(booking),
        traveler_name=traveler.display_name or traveler.phone if traveler else None,
        traveler_avatar=traveler.avatar_url if traveler else None,
        booking_title=title,
        provider_id=provider_id,
        provider_name=provider.display_name or provider.phone if provider else None,
    )


@router.put("/{booking_id}/status", response_model=BookingDetail)
async def update_booking_status(
    booking_id: uuid.UUID,
    body: BookingStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise NotFoundException(message="Booking not found")

    entity, provider_id, title = await _resolve_entity(db, booking.entity_type, booking.entity_id)
    if not provider_id:
        raise BadRequestException(message="Circuit bookings cannot be managed yet")

    is_traveler = booking.traveler_id == current_user.id
    is_provider = provider_id == current_user.id
    if not is_traveler and not is_provider:
        raise ForbiddenException(message="You cannot update this booking")

    old_status = booking.status
    new_status = body.status

    if old_status == "cancelled":
        raise BadRequestException(message="Cannot update a cancelled booking")

    valid_transitions = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["completed", "cancelled"],
        "completed": [],
    }
    allowed = cast(list[str], valid_transitions.get(old_status, []))
    if new_status not in allowed:
        raise BadRequestException(message=f"Cannot change from '{old_status}' to '{new_status}'")
    if is_traveler and new_status != "cancelled":
        raise BadRequestException(message="Travelers can only cancel bookings")

    booking.status = new_status
    await db.flush()

    notification_type_map = {
        "confirmed": "booking_confirmed",
        "completed": "booking_completed",
        "cancelled": "booking_cancelled",
    }
    notify_type = notification_type_map.get(new_status, "booking_cancelled")
    notify_user = booking.traveler_id if is_provider else provider_id
    notify_title = f"Booking {new_status}"
    notify_message = f"Your booking for '{title}' has been {new_status}"

    await _notify(
        db,
        user_id=notify_user,
        type=notify_type,
        title=notify_title,
        message=notify_message,
        reference_type="booking",
        reference_id=booking.id,
    )
    await db.commit()
    await db.refresh(booking)

    traveler = await db.get(User, booking.traveler_id)
    provider = await db.get(User, provider_id) if provider_id else None

    return BookingDetail(
        booking=BookingRead.model_validate(booking),
        traveler_name=traveler.display_name or traveler.phone if traveler else None,
        traveler_avatar=traveler.avatar_url if traveler else None,
        booking_title=title,
        provider_id=provider_id,
        provider_name=provider.display_name or provider.phone if provider else None,
    )
