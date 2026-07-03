import logging
import statistics

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.price_report import PriceReport
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.price_report import (
    PriceEstimateResponse,
    PriceRange,
    PriceReportCreate,
    PriceReportFeed,
    PriceReportRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prices", tags=["Price Reports"])


def _compute_range(prices: list[float]) -> PriceRange | None:
    if not prices:
        return None
    return PriceRange(
        min=min(prices),
        max=max(prices),
        median=round(statistics.median(prices), 0),
        count=len(prices),
    )


def _build_advice(
    origin: str,
    dest: str,
    mode: str,
    range_: PriceRange | None,
) -> str | None:
    if range_ is None:
        return None
    return (
        f"{mode.title()}s from {origin} to {dest} typically cost "
        f"{range_.min:,.0f}–{range_.max:,.0f} DZD "
        f"(median {range_.median:,.0f} DZD, {range_.count} reports). "
        f"Don't pay more than {range_.max:,.0f} DZD."
    )


@router.post("", response_model=PriceReportRead, status_code=201)
async def create_report(
    body: PriceReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.origin_wilaya_id == body.dest_wilaya_id:
        raise BadRequestException(message="Origin and destination must differ")

    for wid in (body.origin_wilaya_id, body.dest_wilaya_id):
        wilaya = await db.get(Wilaya, wid)
        if not wilaya:
            raise NotFoundException(message=f"Wilaya {wid} not found")

    report = PriceReport(
        user_id=current_user.id,
        origin_wilaya_id=body.origin_wilaya_id,
        dest_wilaya_id=body.dest_wilaya_id,
        transport_mode=body.transport_mode,
        price_dzd=body.price_dzd,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return PriceReportRead.model_validate(report)


@router.get("", response_model=PriceReportFeed)
async def list_reports(
    origin_wilaya_id: int | None = Query(None),
    dest_wilaya_id: int | None = Query(None),
    transport_mode: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(PriceReport).order_by(PriceReport.created_at.desc())

    if origin_wilaya_id:
        query = query.where(PriceReport.origin_wilaya_id == origin_wilaya_id)
    if dest_wilaya_id:
        query = query.where(PriceReport.dest_wilaya_id == dest_wilaya_id)
    if transport_mode:
        query = query.where(PriceReport.transport_mode == transport_mode)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    reports = result.scalars().all()

    return PriceReportFeed(
        items=[PriceReportRead.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/estimate", response_model=PriceEstimateResponse)
async def get_estimate(
    origin_wilaya_id: int = Query(...),
    dest_wilaya_id: int = Query(...),
    transport_mode: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if origin_wilaya_id == dest_wilaya_id:
        raise BadRequestException(message="Origin and destination must differ")

    origin = await db.get(Wilaya, origin_wilaya_id)
    dest = await db.get(Wilaya, dest_wilaya_id)
    if not origin or not dest:
        raise NotFoundException(message="Wilaya not found")

    query = select(PriceReport.price_dzd).where(
        PriceReport.origin_wilaya_id == origin_wilaya_id,
        PriceReport.dest_wilaya_id == dest_wilaya_id,
        PriceReport.transport_mode == transport_mode,
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    range_ = _compute_range(prices)

    origin_name = origin.name_en
    dest_name = dest.name_en
    advice = _build_advice(origin_name, dest_name, transport_mode, range_)

    return PriceEstimateResponse(
        origin_wilaya_id=origin_wilaya_id,
        origin_name=origin_name,
        dest_wilaya_id=dest_wilaya_id,
        dest_name=dest_name,
        transport_mode=transport_mode,
        range=range_,
        advice=advice,
    )
