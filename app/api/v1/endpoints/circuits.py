import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.booking import Booking
from app.models.circuit import Circuit, CircuitItem
from app.models.user import User
from app.schemas.booking import BookingDetail, BookingRead
from app.schemas.circuit import CircuitFeed, CircuitRead

router = APIRouter(prefix="/circuits", tags=["Circuits"])


@router.get("", response_model=CircuitFeed)
async def list_circuits(
    wilaya_id: int | None = Query(None),
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Circuit).where(Circuit.is_active == True)
    if wilaya_id:
        q = q.where(Circuit.wilaya_id == wilaya_id)
    if category:
        q = q.where(Circuit.category == category)
    if difficulty:
        q = q.where(Circuit.difficulty == difficulty)
    q = q.order_by(Circuit.duration_days)
    result = await db.execute(q)
    circuits = result.scalars().all()
    return CircuitFeed(items=circuits, total=len(circuits))


@router.get("/{circuit_id}", response_model=CircuitRead)
async def get_circuit(circuit_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    circuit = await db.get(Circuit, circuit_id)
    if not circuit or not circuit.is_active:
        raise NotFoundException(message="Circuit not found")
    return circuit


@router.post("/{circuit_id}/adopt", status_code=201)
async def adopt_circuit(
    circuit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adopt a circuit by creating a Trip with TripItems from circuit items."""
    from app.models.trip import Trip, TripItem

    circuit = await db.get(Circuit, circuit_id)
    if not circuit or not circuit.is_active:
        raise NotFoundException(message="Circuit not found")

    trip = Trip(
        user_id=current_user.id,
        title=f"Trip: {circuit.title}",
        total_days=circuit.duration_days,
    )
    db.add(trip)
    await db.flush()

    for item in circuit.items:
        resolved_type = "poi"
        if item.item_type in ("accommodation", "stay"):
            resolved_type = "stay"
        elif item.item_type == "experience":
            resolved_type = "experience"
        elif item.item_type in ("transport", "travel"):
            resolved_type = "transport_note"

        db.add(TripItem(
            trip_id=trip.id,
            day_number=item.day_number,
            sort_order=item.item_order,
            time_slot=item.time_slot,
            item_type=resolved_type,
            item_id=uuid.uuid4(),
            notes=item.notes,
        ))

    await db.commit()
    return {"id": trip.id, "title": trip.title, "message": "Circuit adopted as trip"}


@router.post("/{circuit_id}/book", response_model=BookingDetail, status_code=201)
async def book_circuit(
    circuit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    circuit = await db.get(Circuit, circuit_id)
    if not circuit or not circuit.is_active:
        raise NotFoundException(message="Circuit not found")

    existing = (
        await db.execute(
            select(Booking).where(
                Booking.traveler_id == current_user.id,
                Booking.entity_type == "circuit",
                Booking.entity_id == circuit_id,
                Booking.status.in_(["pending", "confirmed"]),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise BadRequestException(message="You already have an active booking for this circuit")

    booking = Booking(
        traveler_id=current_user.id,
        entity_type="circuit",
        entity_id=circuit_id,
        status="pending",
        participants=1,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    return BookingDetail(
        booking=BookingRead.model_validate(booking),
        traveler_name=current_user.display_name or current_user.phone,
        booking_title=circuit.title,
    )
