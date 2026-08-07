"""Artisan CRUD — craftspeople register their workshops on the marketplace."""

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.artisan import Artisan
from app.models.user import User
from app.schemas.artisan import ArtisanCreate, ArtisanFeed, ArtisanRead, ArtisanUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/artisans", tags=["Artisans"])


@router.post(
    "",
    response_model=ArtisanRead,
    status_code=201,
    summary="Create an artisan profile",
    description=(
        "Register a craft workshop. A user can have at most one artisan profile; creating one "
        "auto-promotes a traveler account to the artisan role."
    ),
    responses={
        401: {"description": "Authentication required"},
        409: {"description": "You already have an artisan profile"},
        422: {"description": "Validation error"},
    },
)
async def create_artisan(
    body: ArtisanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Artisan).where(Artisan.user_id == current_user.id))
    if existing.scalar_one_or_none():
        raise ConflictException(message="You already have an artisan profile")

    artisan = Artisan(user_id=current_user.id, **body.model_dump())
    db.add(artisan)
    await db.commit()
    await db.refresh(artisan)

    if current_user.role == "traveler":
        current_user.role = "artisan"
        await db.commit()

    return ArtisanRead.model_validate(artisan)


@router.get(
    "",
    response_model=ArtisanFeed,
    summary="List artisans",
    description="Paginated artisans filtered by wilaya, craft type, visitor acceptance, and name search. Sort by name, newest, or years of experience.",  # noqa: E501
    responses={422: {"description": "Validation error"}},
)
async def list_artisans(
    wilaya_id: int | None = Query(None),
    craft_type: str | None = Query(None),
    accepts_visitors: bool | None = Query(None),
    search: str | None = Query(None, max_length=200),
    sort: str = Query("name", pattern="^(name|newest|experience)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    q = select(Artisan)

    if wilaya_id:
        q = q.where(Artisan.wilaya_id == wilaya_id)
    if craft_type:
        q = q.where(Artisan.craft_type == craft_type)
    if accepts_visitors is not None:
        q = q.where(Artisan.accepts_visitors == accepts_visitors)
    if search:
        q = q.where(Artisan.name.ilike(f"%{search}%"))

    if sort == "newest":
        q = q.order_by(Artisan.created_at.desc())
    elif sort == "experience":
        q = q.order_by(Artisan.years_experience.desc().nullslast())
    else:
        q = q.order_by(Artisan.name)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(q.offset(offset).limit(page_size))
    items = [ArtisanRead.model_validate(a) for a in result.scalars().all()]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return ArtisanFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get(
    "/{artisan_id}",
    response_model=ArtisanRead,
    summary="Get an artisan",
    description="Artisan detail. Public.",
    responses={
        404: {"description": "Artisan not found"},
        422: {"description": "Invalid UUID"},
    },
)
async def get_artisan(artisan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    artisan = await db.get(Artisan, artisan_id)
    if not artisan:
        raise NotFoundException(message="Artisan not found")
    return ArtisanRead.model_validate(artisan)


@router.put(
    "/{artisan_id}",
    response_model=ArtisanRead,
    summary="Update an artisan",
    description="Update an artisan profile. Only the owner or an admin can edit.",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "You can only edit your own artisan profile"},
        404: {"description": "Artisan not found"},
    },
)
async def update_artisan(
    artisan_id: uuid.UUID,
    body: ArtisanUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artisan = await db.get(Artisan, artisan_id)
    if not artisan:
        raise NotFoundException(message="Artisan not found")
    if artisan.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only edit your own artisan profile")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(artisan, field, value)
    await db.commit()
    await db.refresh(artisan)
    return ArtisanRead.model_validate(artisan)


@router.delete(
    "/{artisan_id}",
    status_code=204,
    summary="Delete an artisan",
    description="Delete an artisan profile. Only the owner or an admin can delete.",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "You can only delete your own artisan profile"},
        404: {"description": "Artisan not found"},
    },
)
async def delete_artisan(
    artisan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artisan = await db.get(Artisan, artisan_id)
    if not artisan:
        raise NotFoundException(message="Artisan not found")
    if artisan.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete your own artisan profile")
    await db.delete(artisan)
    await db.commit()
