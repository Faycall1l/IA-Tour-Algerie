"""Personalized recommendations based on user preferences and history."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_vector_search
from app.models.artisan import Artisan
from app.models.experience import Experience
from app.models.favorite import Favorite
from app.models.poi import POI
from app.models.preference import UserPreference
from app.models.stay import Stay
from app.models.user import User
from app.schemas.experience import ExperienceRead
from app.schemas.artisan import ArtisanRead
from app.schemas.poi import POIBrief, POIRead
from app.schemas.stay import StayRead
from app.services.vector_search import VectorSearchService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


async def _get_user_preferences(
    current_user: User, db: AsyncSession
) -> UserPreference | None:
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    return result.scalar_one_or_none()


async def _get_user_category_history(
    current_user: User, db: AsyncSession
) -> list[str]:
    """Get categories the user has favorited or visited."""
    fav_result = await db.execute(
        select(POI.category)
        .join(Favorite, Favorite.entity_id == POI.id)
        .where(
            Favorite.user_id == current_user.id,
            Favorite.entity_type == "poi",
            POI.category.isnot(None),
        )
        .distinct()
    )
    return [row[0] for row in fav_result.all()]


@router.get("/pois", response_model=list[POIRead])
async def recommend_pois(
    limit: int = Query(12, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    pref = await _get_user_preferences(current_user, db)
    fav_categories = await _get_user_category_history(current_user, db)

    preferred_cats = []
    if pref and pref.preferred_categories:
        preferred_cats = pref.preferred_categories
    preferred_cats.extend(fav_categories)
    preferred_cats = list(set(preferred_cats))

    query = select(POI)

    if preferred_cats:
        query = query.where(POI.category.in_(preferred_cats))
    query = query.order_by(POI.is_featured.desc(), POI.name.asc())

    # Budget filter
    if pref and pref.budget_level and pref.budget_level in ("budget", "moderate"):
        query = query.where(
            (POI.entry_fee_dzd.is_(None)) | (POI.entry_fee_dzd <= 500)
        )

    query = query.limit(limit)
    result = await db.execute(query)
    pois = result.scalars().all()

    from app.api.v1.endpoints.pois import _attach_ratings
    return await _attach_ratings(db, pois)


@router.get("/experiences", response_model=list[ExperienceRead])
async def recommend_experiences(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _vector_search: VectorSearchService = Depends(get_vector_search),
):
    pref = await _get_user_preferences(current_user, db)

    query = select(Experience).where(Experience.status == "active")

    if pref:
        if pref.travel_style == "solo":
            query = query.where(
                (Experience.max_participants.is_(None)) | (Experience.max_participants <= 5)
            )
        elif pref.travel_style == "family":
            query = query.where(
                (Experience.max_participants.is_(None)) | (Experience.max_participants >= 4)
            )
        if pref.budget_level in ("budget", "moderate"):
            query = query.where(
                (Experience.price_dzd.is_(None)) | (Experience.price_dzd <= 5000)
            )

    query = query.order_by(Experience.is_verified.desc(), Experience.completion_count.desc()).limit(limit)
    result = await db.execute(query)
    return [ExperienceRead.model_validate(e) for e in result.scalars().all()]


@router.get("/stays", response_model=list[StayRead])
async def recommend_stays(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await _get_user_preferences(current_user, db)

    query = select(Stay).where(Stay.is_active.is_(True))

    if pref:
        if pref.travel_style == "solo":
            query = query.where(
                (Stay.max_guests.is_(None)) | (Stay.max_guests <= 2)
            )
        elif pref.travel_style == "family":
            query = query.where(
                (Stay.max_guests.is_(None)) | (Stay.max_guests >= 4)
            )
        elif pref.travel_style == "group":
            query = query.where(
                (Stay.max_guests.is_(None)) | (Stay.max_guests >= 6)
            )
        if pref.budget_level == "budget":
            query = query.where(Stay.price_per_night_dzd <= 3000)
        elif pref.budget_level == "moderate":
            query = query.where(Stay.price_per_night_dzd <= 8000)
        elif pref.budget_level == "luxury":
            query = query.where(Stay.price_per_night_dzd >= 10000)

    query = query.order_by(Stay.price_per_night_dzd.asc()).limit(limit)
    result = await db.execute(query)
    return [StayRead.model_validate(s) for s in result.scalars().all()]


@router.get("/artisans", response_model=list[ArtisanRead])
async def recommend_artisans(
    wilaya_id: int | None = Query(None),
    craft_type: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = await _get_user_preferences(current_user, db)
    fav_categories = await _get_user_category_history(current_user, db)

    query = select(Artisan)

    if wilaya_id:
        query = query.where(Artisan.wilaya_id == wilaya_id)

    if craft_type:
        query = query.where(Artisan.craft_type == craft_type)
    elif pref and pref.preferred_categories:
        craft_map = {
            "market": ["pottery", "carpet_weaving", "textile", "basket_weaving", "embroidery"],
            "cultural": ["calligraphy", "tilework", "stone_carving"],
            "historical": ["metalwork", "copper_work", "leather_work", "woodwork"],
            "museum": ["jewelry", "glasswork"],
        }
        matching_crafts = []
        for cat in pref.preferred_categories:
            matching_crafts.extend(craft_map.get(cat, []))
        if matching_crafts:
            query = query.where(Artisan.craft_type.in_(list(set(matching_crafts))))

    query = query.order_by(Artisan.is_verified.desc(), Artisan.years_experience.desc().nullslast()).limit(limit)
    result = await db.execute(query)
    return [ArtisanRead.model_validate(a) for a in result.scalars().all()]
