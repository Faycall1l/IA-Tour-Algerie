import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional, get_db
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.stay import Stay
from app.models.user import User
from app.schemas.stay import StayCreate, StayFeed, StayRead, StayUpdate

router = APIRouter(prefix="/stays", tags=["Stays"])


@router.post("", response_model=StayRead, status_code=201)
async def create_stay(
    body: StayCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("hotel", "agency", "admin"):
        raise ForbiddenException(message="Only hotels and agencies can list stays")

    stay = Stay(provider_id=current_user.id, **body.model_dump())
    db.add(stay)
    await db.commit()
    await db.refresh(stay)
    stay.provider_name = current_user.display_name
    stay.provider_avatar = current_user.avatar_url
    return stay


@router.get("", response_model=StayFeed)
async def list_stays(
    wilaya_id: int | None = Query(None),
    property_type: str | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Stay).where(Stay.is_active.is_(True))

    if wilaya_id:
        query = query.where(Stay.wilaya_id == wilaya_id)
    if property_type:
        query = query.where(Stay.property_type == property_type)
    if min_price is not None:
        query = query.where(Stay.price_per_night_dzd >= min_price)
    if max_price is not None:
        query = query.where(Stay.price_per_night_dzd <= max_price)

    query = query.order_by(Stay.created_at.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    stays = result.scalars().all()

    provider_ids = {s.provider_id for s in stays}
    if provider_ids:
        users = (await db.execute(select(User).where(User.id.in_(provider_ids)))).scalars().all()
        user_map = {u.id: u for u in users}
    else:
        user_map = {}

    items = []
    for s in stays:
        user = user_map.get(s.provider_id)
        read = StayRead.model_validate(s)
        read.provider_name = user.display_name if user else None
        read.provider_avatar = user.avatar_url if user else None
        items.append(read)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return StayFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/{stay_id}", response_model=StayRead)
async def get_stay(
    stay_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    stay = await db.get(Stay, stay_id)
    if not stay or not stay.is_active:
        raise NotFoundException(message="Stay not found")

    user = await db.get(User, stay.provider_id)
    read = StayRead.model_validate(stay)
    read.provider_name = user.display_name if user else None
    read.provider_avatar = user.avatar_url if user else None

    if current_user:
        from app.models.favorite import Favorite
        from app.models.visit import Visit
        from sqlalchemy import select

        fav = await db.execute(
            select(Favorite).where(
                Favorite.user_id == current_user.id,
                Favorite.entity_type == "stay",
                Favorite.entity_id == stay_id,
            )
        )
        read.is_favorited = fav.scalar_one_or_none() is not None

        vis = await db.execute(
            select(Visit).where(
                Visit.user_id == current_user.id,
                Visit.entity_type == "stay",
                Visit.entity_id == stay_id,
            )
        )
        read.has_visited = vis.scalar_one_or_none() is not None

    return read


@router.put("/{stay_id}", response_model=StayRead)
async def update_stay(
    stay_id: uuid.UUID,
    body: StayUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stay = await db.get(Stay, stay_id)
    if not stay:
        raise NotFoundException(message="Stay not found")
    if stay.provider_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="Not your stay listing")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(stay, field, value)

    await db.commit()
    await db.refresh(stay)
    read = StayRead.model_validate(stay)
    read.provider_name = current_user.display_name
    read.provider_avatar = current_user.avatar_url
    return read


@router.delete("/{stay_id}", status_code=204)
async def delete_stay(
    stay_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stay = await db.get(Stay, stay_id)
    if not stay:
        raise NotFoundException(message="Stay not found")
    if stay.provider_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="Not your stay listing")

    await db.delete(stay)
    await db.commit()
