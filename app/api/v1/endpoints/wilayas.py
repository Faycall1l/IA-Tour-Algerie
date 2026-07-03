import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundException
from app.models.wilaya import Wilaya
from app.schemas.wilaya import WilayaRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wilayas", tags=["Wilayas"])


@router.get("", response_model=list[WilayaRead])
async def list_wilayas(
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Wilaya).order_by(Wilaya.id)
    if search:
        query = query.where(
            Wilaya.name_fr.ilike(f"%{search}%")
            | Wilaya.name_ar.ilike(f"%{search}%")
            | Wilaya.name_en.ilike(f"%{search}%")
        )
    result = await db.execute(query)
    wilayas = result.scalars().all()
    return [WilayaRead.model_validate(w) for w in wilayas]


@router.get("/{wilaya_id}", response_model=WilayaRead)
async def get_wilaya(wilaya_id: int, db: AsyncSession = Depends(get_db)):
    wilaya = await db.get(Wilaya, wilaya_id)
    if not wilaya:
        raise NotFoundException(message="Wilaya not found")
    return WilayaRead.model_validate(wilaya)
