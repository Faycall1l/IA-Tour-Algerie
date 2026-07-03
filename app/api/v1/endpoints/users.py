import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.provider_profile import PROVIDER_TYPES, ProviderProfile
from app.models.user import User
from app.schemas.provider_profile import (
    ProviderProfileRead,
    ProviderProfileUpdate,
    ProviderUserRead,
)
from app.schemas.user import RoleUpdate, UserRead, UserUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return UserRead.model_validate(current_user)


@router.put("/me", response_model=UserRead)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.put("/me/role", response_model=UserRead)
async def set_role(
    body: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_role = current_user.role
    current_user.role = body.role

    if body.role in PROVIDER_TYPES and old_role not in PROVIDER_TYPES:
        profile = await db.execute(
            select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
        )
        if not profile.scalar_one_or_none():
            db.add(ProviderProfile(user_id=current_user.id, provider_type=body.role))
    elif body.role not in PROVIDER_TYPES and old_role in PROVIDER_TYPES:
        profile = await db.execute(
            select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
        )
        existing = profile.scalar_one_or_none()
        if existing:
            await db.delete(existing)

    await db.commit()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.put("/me/profile", response_model=ProviderUserRead)
async def update_profile(
    body: ProviderProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in PROVIDER_TYPES:
        raise BadRequestException(message="You must set your role to a provider type first")

    result = await db.execute(
        select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise BadRequestException(message="No profile found. Set your role first.")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(current_user)
    await db.refresh(profile)

    return ProviderUserRead(
        **UserRead.model_validate(current_user).model_dump(),
        profile=ProviderProfileRead.model_validate(profile),
    )


@router.get("/providers", response_model=list[ProviderUserRead])
async def list_providers(
    role: str | None = Query(None, pattern=f"^({'|'.join(PROVIDER_TYPES)})$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).options(joinedload(User.profile)).where(User.role.in_(PROVIDER_TYPES))
    if role:
        query = query.where(User.role == role)

    result = await db.execute(
        query.order_by(User.display_name).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.unique().scalars().all()

    items = []
    for u in users:
        items.append(
            ProviderUserRead(
                **UserRead.model_validate(u).model_dump(),
                profile=ProviderProfileRead.model_validate(u.profile) if u.profile else None,
            )
        )

    return items


@router.get("/providers/{user_id}", response_model=ProviderUserRead)
async def get_provider(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .options(joinedload(User.profile))
        .where(User.id == user_id, User.role.in_(PROVIDER_TYPES))
    )
    user = result.unique().scalar_one_or_none()
    if not user:
        raise NotFoundException(message="Provider not found")

    return ProviderUserRead(
        **UserRead.model_validate(user).model_dump(),
        profile=ProviderProfileRead.model_validate(user.profile) if user.profile else None,
    )
