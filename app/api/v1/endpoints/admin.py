import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db, get_vector_search
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.models.experience import Experience
from app.models.live_post import LivePost
from app.models.poi import POI
from app.models.price_report import PriceReport
from app.models.provider_profile import PROVIDER_TYPES, ProviderProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.admin import (
    AdminActionResponse,
    AdminRoleUpdate,
    PriceReportAdminFeed,
    PriceReportAdminRead,
    ProviderAdminFeed,
    ProviderProfileAdminRead,
    StatsDashboard,
    UserAdminFeed,
    UserAdminRead,
    WilayaCount,
    CategoryCount,
)
from app.schemas.user import UserRead
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Dashboard Stats ────────────────────────────────────────────────


@router.get("/stats", response_model=StatsDashboard)
async def dashboard_stats(
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.booking import Booking
    from app.models.event import Event
    from app.models.experience import Experience
    from app.models.poi import POI
    from app.models.review import Review
    from app.models.stay import Stay
    from app.models.trip import Trip
    from app.models.user import User

    total_pois = (await db.execute(select(func.count(POI.id)))).scalar() or 0
    total_stays = (await db.execute(select(func.count(Stay.id)))).scalar() or 0
    total_experiences = (await db.execute(select(func.count(Experience.id)))).scalar() or 0
    total_events = (await db.execute(select(func.count(Event.id)))).scalar() or 0
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_reviews = (await db.execute(select(func.count(Review.id)))).scalar() or 0
    total_bookings = (await db.execute(select(func.count(Booking.id)))).scalar() or 0
    total_trips = (await db.execute(select(func.count(Trip.id)))).scalar() or 0

    wilaya_rows = (
        await db.execute(
            select(POI.wilaya_id, func.count(POI.id).label("cnt"))
            .group_by(POI.wilaya_id)
            .order_by(POI.wilaya_id)
        )
    ).all()
    pois_per_wilaya = [WilayaCount(wilaya_id=r[0], count=r[1]) for r in wilaya_rows]

    category_rows = (
        await db.execute(
            select(POI.category, func.count(POI.id).label("cnt"))
            .group_by(POI.category)
            .order_by(func.count(POI.id).desc())
        )
    ).all()
    pois_per_category = [CategoryCount(category=r[0], count=r[1]) for r in category_rows]

    return StatsDashboard(
        total_pois=total_pois,
        total_stays=total_stays,
        total_experiences=total_experiences,
        total_events=total_events,
        total_users=total_users,
        total_reviews=total_reviews,
        total_bookings=total_bookings,
        total_trips=total_trips,
        pois_per_wilaya=pois_per_wilaya,
        pois_per_category=pois_per_category,
    )


# ── Price Reports ──────────────────────────────────────────────────


@router.get("/price-reports", response_model=PriceReportAdminFeed)
async def list_price_reports(
    verified: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(PriceReport).order_by(PriceReport.created_at.desc())

    if verified is True:
        query = query.where(PriceReport.confidence == "verified")
    elif verified is False:
        query = query.where(PriceReport.confidence == "user")

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    reports = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PriceReportAdminFeed(
        items=[PriceReportAdminRead.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.put("/price-reports/{report_id}/verify", response_model=AdminActionResponse)
async def verify_price_report(
    report_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(PriceReport, report_id)
    if not report:
        raise NotFoundException(message="Price report not found")

    report.confidence = "verified"
    report.verified_at = date.today().isoformat()
    await db.commit()

    return AdminActionResponse(message="Price report verified")


@router.delete("/price-reports/{report_id}", response_model=AdminActionResponse)
async def reject_price_report(
    report_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(PriceReport, report_id)
    if not report:
        raise NotFoundException(message="Price report not found")

    await db.delete(report)
    await db.commit()

    return AdminActionResponse(message="Price report rejected and deleted")


# ── Users ──────────────────────────────────────────────────────────


@router.get("/users", response_model=UserAdminFeed)
async def list_users(
    role: str | None = Query(None),
    verified: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())

    if role:
        query = query.where(User.role == role)
    if verified is True:
        query = query.where(User.is_verified)
    elif verified is False:
        query = query.where(~User.is_verified)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return UserAdminFeed(
        items=[UserAdminRead.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.put("/users/{user_id}/role", response_model=UserRead)
async def set_user_role(
    user_id: uuid.UUID,
    body: AdminRoleUpdate,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundException(message="User not found")

    old_role = user.role
    user.role = body.role

    if body.role in PROVIDER_TYPES and old_role not in PROVIDER_TYPES:
        result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == user.id))
        if not result.scalar_one_or_none():
            db.add(ProviderProfile(user_id=user.id, provider_type=body.role))
    elif body.role not in PROVIDER_TYPES and old_role in PROVIDER_TYPES:
        result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == user.id))
        profile = result.scalar_one_or_none()
        if profile:
            await db.delete(profile)

    await db.commit()
    await db.refresh(user)

    return UserRead.model_validate(user)


@router.put("/users/{user_id}/verify", response_model=UserRead)
async def toggle_user_verification(
    user_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundException(message="User not found")

    user.is_verified = not user.is_verified
    await db.commit()
    await db.refresh(user)

    return UserRead.model_validate(user)


# ── Provider Profiles ──────────────────────────────────────────────


@router.get("/providers", response_model=ProviderAdminFeed)
async def list_providers(
    verified: bool | None = Query(None),
    provider_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(ProviderProfile).order_by(ProviderProfile.id)

    if verified is True:
        query = query.where(ProviderProfile.is_verified)
    elif verified is False:
        query = query.where(~ProviderProfile.is_verified)
    if provider_type:
        query = query.where(ProviderProfile.provider_type == provider_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    profiles = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return ProviderAdminFeed(
        items=[ProviderProfileAdminRead.model_validate(p) for p in profiles],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.put("/providers/{profile_id}/approve", response_model=AdminActionResponse)
async def approve_provider(
    profile_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise NotFoundException(message="Provider profile not found")

    profile.is_verified = True
    await db.commit()

    return AdminActionResponse(message="Provider profile approved")


# ── Content Moderation ─────────────────────────────────────────────


@router.delete("/reviews/{review_id}", response_model=AdminActionResponse)
async def admin_delete_review(
    review_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    review = await db.get(Review, review_id)
    if not review:
        raise NotFoundException(message="Review not found")

    await db.delete(review)
    await db.commit()

    return AdminActionResponse(message="Review deleted")


@router.delete("/live-posts/{post_id}", response_model=AdminActionResponse)
async def admin_delete_live_post(
    post_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(LivePost, post_id)
    if not post:
        raise NotFoundException(message="Live post not found")

    await db.delete(post)
    await db.commit()

    return AdminActionResponse(message="Live post deleted")


@router.put("/live-posts/{post_id}/moderate", response_model=AdminActionResponse)
async def moderate_live_post(
    post_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(LivePost, post_id)
    if not post:
        raise NotFoundException(message="Live post not found")

    post.is_moderated = True
    await db.commit()

    return AdminActionResponse(message="Live post marked as moderated")


@router.delete("/experiences/{experience_id}", response_model=AdminActionResponse)
async def admin_delete_experience(
    experience_id: uuid.UUID,
    _current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    experience = await db.get(Experience, experience_id)
    if not experience:
        raise NotFoundException(message="Experience not found")

    await db.delete(experience)
    await db.commit()
    vector_search.delete_experience(experience_id)

    return AdminActionResponse(message="Experience deleted")


# ── Data Verification ──


@router.get("/verify/poi/{poi_id}", response_model=AdminActionResponse)
async def verify_poi_quality(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_admin),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="POI not found")

    try:
        from app.agents.verification import create_verification_agent, verify_poi_dry_run

        agent = create_verification_agent(
            api_key=settings.agent.openrouter_api_key or "",
            model_name=settings.agent.openrouter_model or "",
        )

        if agent:
            # LLM-based verification
            result = await agent.run(
                f"name: {poi.name}\ncategory: {poi.category}\ndescription: {poi.description}\n"
                f"osm_tags: {poi.osm_tags}\nlat: {poi.latitude}\nlng: {poi.longitude}"
            )
        else:
            # Dry-run with rule-based checks
            result = await verify_poi_dry_run(
                poi_id=str(poi.id),
                name=poi.name,
                category=poi.category,
                description=poi.description,
                osm_tags=poi.osm_tags,
            )

        return AdminActionResponse(
            message=f"Verification complete: score={result.score}/5, "
                    f"issues={len(result.issues)}, missing={result.missing_fields}"
        )
    except Exception as exc:
        logger.warning("Verification failed for POI %s: %s", poi_id, exc)
        return AdminActionResponse(message=f"Verification error: {exc}")


@router.get("/verify/stats", response_model=AdminActionResponse)
async def get_verification_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_admin),
):
    total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0
    with_phone = (await db.execute(select(func.count()).where(POI.phone.isnot(None)))).scalar() or 0
    with_website = (await db.execute(select(func.count()).where(POI.website.isnot(None)))).scalar() or 0
    with_hours = (await db.execute(select(func.count()).where(POI.opening_hours.isnot(None)))).scalar() or 0
    short_desc = (await db.execute(
        select(func.count()).where(POI.description.isnot(None), func.length(POI.description) < 80)
    )).scalar() or 0

    return AdminActionResponse(
        message=f"POI data quality stats: {total} total, {with_phone} with phone, "
                f"{with_website} with website, {with_hours} with hours, "
                f"{short_desc} with short descriptions"
    )
