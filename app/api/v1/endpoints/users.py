import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.booking import Booking
from app.models.experience import Experience
from app.models.provider_profile import PROVIDER_TYPES, ProviderProfile
from app.models.review import Review
from app.models.stay import Stay
from app.models.user import User
from app.schemas.provider_dashboard import (
    DashboardBookingSummary,
    DashboardExperienceSummary,
    DashboardReviewSummary,
    DashboardStaySummary,
    ProviderDashboard,
)
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


@router.get("/me/dashboard", response_model=ProviderDashboard)
async def provider_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated dashboard for providers: listings, bookings, reviews, metrics."""
    if current_user.role not in ("admin", *PROVIDER_TYPES):
        raise ForbiddenException(message="Provider access required")

    profile = None
    result = await db.execute(
        select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    # Experiences
    exp_result = await db.execute(
        select(Experience).where(Experience.provider_id == current_user.id)
    )
    experiences = exp_result.scalars().all()
    active_experiences = [e for e in experiences if e.status == "active"]

    # Stays
    stay_result = await db.execute(
        select(Stay).where(Stay.provider_id == current_user.id)
    )
    stays = stay_result.scalars().all()
    active_stays = [s for s in stays if s.is_active]

    # Bookings (via experience IDs)
    exp_ids = [e.id for e in experiences]
    booking_count = 0
    pending_count = 0
    confirmed_count = 0
    completed_count = 0
    recent_bookings_raw = []

    if exp_ids:
        booking_q = (
            select(Booking, User.display_name, User.phone)
            .join(User, Booking.traveler_id == User.id)
            .where(Booking.entity_type == "experience", Booking.entity_id.in_(exp_ids))
            .order_by(Booking.created_at.desc())
        )
        booking_result = await db.execute(booking_q.limit(10))
        recent_bookings_raw = booking_result.all()

        all_bookings = await db.execute(
            select(Booking).where(Booking.entity_type == "experience", Booking.entity_id.in_(exp_ids))
        )
        for b in all_bookings.scalars().all():
            booking_count += 1
            if b.status == "pending":
                pending_count += 1
            elif b.status == "confirmed":
                confirmed_count += 1
            elif b.status == "completed":
                completed_count += 1

    # Reviews on experiences
    review_q = (
        select(Review, User.display_name, User.phone)
        .join(User, Review.user_id == User.id)
        .where(Review.experience_id.in_(exp_ids) if exp_ids else Review.id.is_(None))
        .order_by(Review.created_at.desc())
    )
    review_result = await db.execute(review_q.limit(10))
    recent_reviews_raw = review_result.all()

    # Also reviews on stays
    stay_ids = [s.id for s in stays]
    if stay_ids:
        stay_review_q = (
            select(Review, User.display_name, User.phone)
            .join(User, Review.user_id == User.id)
            .where(Review.stay_id.in_(stay_ids))
            .order_by(Review.created_at.desc())
        )
        stay_review_result = await db.execute(stay_review_q.limit(10))
        stay_reviews_raw = stay_review_result.all()
        recent_reviews_raw = list(recent_reviews_raw) + list(stay_reviews_raw)
        recent_reviews_raw.sort(key=lambda r: r[0].created_at, reverse=True)
        recent_reviews_raw = recent_reviews_raw[:10]

    # Aggregate review stats
    total_reviews = len(recent_reviews_raw)
    scores = [r[0].overall_score for r in recent_reviews_raw]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    unresponded = sum(1 for r, _, _ in recent_reviews_raw if not r.owner_response)

    # Build response
    recent_bookings = []
    entity_titles = {}
    for b, display_name, phone in recent_bookings_raw:
        if b.entity_id not in entity_titles:
            exp = next((e for e in experiences if e.id == b.entity_id), None)
            entity_titles[b.entity_id] = exp.title if exp else str(b.entity_id)
        recent_bookings.append(DashboardBookingSummary(
            id=b.id,
            entity_type=b.entity_type,
            entity_id=b.entity_id,
            entity_title=entity_titles[b.entity_id],
            traveler_name=display_name or phone,
            status=b.status,
            participants=b.participants,
            requested_date=str(b.requested_date) if b.requested_date else None,
            created_at=b.created_at,
        ))

    recent_reviews = []
    for r, display_name, phone in recent_reviews_raw:
        if r.experience_id:
            exp = next((e for e in experiences if e.id == r.experience_id), None)
            title = exp.title if exp else str(r.experience_id)
            etype = "experience"
        elif r.stay_id:
            stay = next((s for s in stays if s.id == r.stay_id), None)
            title = stay.name if stay else str(r.stay_id)
            etype = "stay"
        else:
            title = "POI"
            etype = "poi"
        recent_reviews.append(DashboardReviewSummary(
            id=r.id,
            entity_type=etype,
            entity_title=title,
            reviewer_name=display_name or phone,
            overall_score=r.overall_score,
            text=r.text,
            has_response=bool(r.owner_response),
            created_at=r.created_at,
        ))

    top_experiences = [
        DashboardExperienceSummary(
            id=e.id, title=e.title, category=e.category, wilaya_id=e.wilaya_id,
            status=e.status, price_dzd=e.price_dzd, photo_count=len(e.photos or []),
        )
        for e in active_experiences[:5]
    ]
    top_stays = [
        DashboardStaySummary(
            id=s.id, name=s.name, property_type=s.property_type, wilaya_id=s.wilaya_id,
            is_active=s.is_active, price_per_night_dzd=s.price_per_night_dzd,
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
        total_bookings=booking_count,
        pending_bookings=pending_count,
        confirmed_bookings=confirmed_count,
        completed_bookings=completed_count,
        total_reviews=total_reviews,
        average_score=avg_score,
        unresponded_reviews=unresponded,
        recent_bookings=recent_bookings,
        recent_reviews=recent_reviews,
        top_experiences=top_experiences,
        top_stays=top_stays,
    )
