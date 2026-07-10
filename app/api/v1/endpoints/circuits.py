import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundException
from app.models.circuit import Circuit, CircuitItem
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
