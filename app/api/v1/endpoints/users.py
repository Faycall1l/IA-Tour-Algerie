import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.experience import Experience
from app.models.provider_profile import PROVIDER_TYPES, ProviderProfile
from app.models.stay import Stay
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.wilaya import Wilaya
from app.schemas.provider_dashboard import (
    DashboardExperienceSummary,
    DashboardStaySummary,
    ProviderDashboard,
)
from app.schemas.provider_profile import (
    ProviderProfileRead,
    ProviderProfileUpdate,
    ProviderUserRead,
)
from app.schemas.user import (
    SELF_ASSIGNABLE_ROLES,
    RoleUpdate,
    UserProfileRead,
    UserProfileUpdate,
    UserRead,
    UserUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current user",
    description="Return the authenticated user's profile, including role, verification status, and provider profile link.",  # noqa: E501
    responses={401: {"description": "Authentication required"}},
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return UserRead.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserRead,
    summary="Update current user",
    description="Update the authenticated user's profile fields. Role changes must use PUT /users/me/role.",  # noqa: E501
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Validation error"},
    },
)
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


@router.put(
    "/me/role",
    response_model=UserRead,
    summary="Switch role",
    description=(
        "Self-assign a role. Restricted to SELF_ASSIGNABLE_ROLES (traveler/guide/agency/hotel); "
        "the `admin` role cannot be self-assigned. Switching to a provider role auto-creates a "
        "provider profile, and switching away deletes it."
    ),
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Role cannot be self-assigned"},
    },
)
async def set_role(
    body: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    old_role = current_user.role
    if body.role not in SELF_ASSIGNABLE_ROLES:
        raise ForbiddenException(message="Role cannot be self-assigned")
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


@router.put(
    "/me/profile",
    response_model=ProviderUserRead,
    summary="Update provider profile",
    description=(
        "Update the authenticated user's provider profile (company name, website, experience, "
        "team size, etc.). The user must already have a provider role."
    ),
    responses={
        400: {"description": "No provider profile — set your role to a provider type first"},
        401: {"description": "Authentication required"},
    },
)
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


async def _read_traveler_profile(
    db: AsyncSession, current_user: User
) -> tuple[UserProfile, str | None]:
    """Load the traveler profile (create-on-first-use) + resolved home wilaya name."""
    from app.agents.profile import load_or_create_profile

    profile = await load_or_create_profile(db, current_user.id)
    wilaya_name = None
    if profile.home_wilaya_id:
        wilaya = await db.get(Wilaya, profile.home_wilaya_id)
        wilaya_name = wilaya.name_fr if wilaya else None
    return profile, wilaya_name


def _profile_read(profile: UserProfile, wilaya_name: str | None) -> UserProfileRead:
    return UserProfileRead(
        user_id=profile.user_id,
        budget_level=profile.budget_level,
        interests=profile.interests,
        home_wilaya_id=profile.home_wilaya_id,
        home_wilaya_name=wilaya_name,
        travel_style=profile.travel_style,
        preferred_language=profile.preferred_language,
        notes=profile.notes,
        updated_at=profile.updated_at,
    )


@router.get(
    "/me/traveler-profile",
    response_model=UserProfileRead,
    summary="Get traveler profile",
    description=(
        "Return the authenticated user's persistent traveler profile (budget, interests, home "
        "wilaya, style). This is what the agent pipeline mines from conversations and injects "
        "into prompts across sessions. Created empty on first access."
    ),
    responses={401: {"description": "Authentication required"}},
)
async def get_traveler_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's persistent traveler profile."""
    profile, wilaya_name = await _read_traveler_profile(db, current_user)
    await db.commit()
    return _profile_read(profile, wilaya_name)


@router.put(
    "/me/traveler-profile",
    response_model=UserProfileRead,
    summary="Update traveler profile",
    description=(
        "Update the authenticated user's persistent traveler profile. Values set explicitly "
        "replace the mined values; omitted fields are left unchanged."
    ),
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Validation error"},
    },
)
async def update_traveler_profile(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's persistent traveler profile."""
    profile, wilaya_name = await _read_traveler_profile(db, current_user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    if body.home_wilaya_id is not None:
        wilaya = await db.get(Wilaya, body.home_wilaya_id)
        wilaya_name = wilaya.name_fr if wilaya else None
    await db.commit()
    await db.refresh(profile)
    return _profile_read(profile, wilaya_name)


@router.get(
    "/providers",
    response_model=list[ProviderUserRead],
    summary="List providers",
    description="List all provider users (guide/agency/hotel) with their profiles. Public.",
    responses={422: {"description": "Invalid role filter"}},
)
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


@router.get(
    "/providers/{user_id}",
    response_model=ProviderUserRead,
    summary="Get provider",
    description="Return a single provider user with their profile. Public.",
    responses={404: {"description": "Provider not found"}},
)
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


@router.get(
    "/me/dashboard",
    response_model=ProviderDashboard,
    summary="Provider dashboard",
    description=(
        "Aggregated dashboard for providers: listing counts (experiences/stays), active counts, "
        "and top 5 of each. Requires a provider role or admin."
    ),
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Provider access required"},
    },
)
async def provider_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated dashboard for providers: listings and metrics."""
    if current_user.role not in ("admin", *PROVIDER_TYPES):
        raise ForbiddenException(message="Provider access required")

    profile = None
    result = await db.execute(
        select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    exp_result = await db.execute(
        select(Experience).where(Experience.provider_id == current_user.id)
    )
    experiences = exp_result.scalars().all()
    active_experiences = [e for e in experiences if e.status == "active"]

    stay_result = await db.execute(select(Stay).where(Stay.provider_id == current_user.id))
    stays = stay_result.scalars().all()
    active_stays = [s for s in stays if s.is_active]

    top_experiences = [
        DashboardExperienceSummary(
            id=e.id,
            title=e.title,
            category=e.category,
            wilaya_id=e.wilaya_id,
            status=e.status,
            price_dzd=e.price_dzd,
            photo_count=len(e.photos or []),
        )
        for e in active_experiences[:5]
    ]
    top_stays = [
        DashboardStaySummary(
            id=s.id,
            name=s.name,
            property_type=s.property_type,
            wilaya_id=s.wilaya_id,
            is_active=s.is_active,
            price_per_night_dzd=s.price_per_night_dzd,
        )
        for s in active_stays[:5]
    ]

    return ProviderDashboard(
        provider_type=profile.provider_type if profile else current_user.role,
        company_name=profile.company_name if profile else None,
        is_verified=profile.is_verified if profile else False,
        total_experiences=len(experiences),
        active_experiences=len(active_experiences),
        total_stays=len(stays),
        active_stays=len(active_stays),
        top_experiences=top_experiences,
        top_stays=top_stays,
    )
