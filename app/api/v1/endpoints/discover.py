import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundException
from app.models.experience import Experience
from app.models.poi import POI
from app.models.review import Review
from app.models.stay import Stay
from app.models.user import User
from app.models.wilaya import Wilaya


def _avg_score(scores: list[int]) -> float | None:
    return round(sum(scores) / len(scores), 1) if scores else None


def _display_name(user_map: dict, user_id: uuid.UUID) -> str | None:
    u = user_map.get(user_id)
    return u.display_name if u else None


def _avatar_url(user_map: dict, user_id: uuid.UUID) -> str | None:
    u = user_map.get(user_id)
    return u.avatar_url if u else None


router = APIRouter(prefix="/discover", tags=["Discover"])


class DiscoverPOI(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None
    latitude: float | None
    longitude: float | None
    photo_url: str | None
    entry_fee_dzd: float | None
    average_score: float | None
    total_reviews: int


class DiscoverExperience(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    description: str | None
    price_dzd: float | None
    duration_hours: float | None
    provider_name: str | None
    provider_avatar: str | None
    meeting_point: str | None
    photos: list[str] | None


class DiscoverStay(BaseModel):
    id: uuid.UUID
    name: str
    property_type: str
    description: str | None
    price_per_night_dzd: float
    amenities: list[str] | None
    photos: list[str] | None
    latitude: float | None
    longitude: float | None
    max_guests: int | None
    provider_name: str | None
    provider_avatar: str | None


class DiscoverResponse(BaseModel):
    wilaya_id: int
    wilaya_name: str
    pois: list[DiscoverPOI]
    experiences: list[DiscoverExperience]
    stays: list[DiscoverStay]


class ExperienceFilterPOI(BaseModel):
    experience_id: uuid.UUID
    title: str
    category: str
    price_dzd: float | None
    duration_hours: float | None
    provider_name: str | None


@router.get("/wilayas/{wilaya_id}", response_model=DiscoverResponse)
async def discover_wilaya(
    wilaya_id: int,
    db: AsyncSession = Depends(get_db),
):
    wilaya = await db.get(Wilaya, wilaya_id)
    if not wilaya:
        raise NotFoundException(message="Wilaya not found")

    # POIs
    pois_rows = (
        (await db.execute(select(POI).where(POI.wilaya_id == wilaya_id).order_by(POI.name)))
        .scalars()
        .all()
    )

    poi_ids = [p.id for p in pois_rows]
    review_scores: dict[uuid.UUID, list[int]] = {}
    if poi_ids:
        rows = (
            await db.execute(
                select(Review.poi_id, Review.overall_score).where(Review.poi_id.in_(poi_ids))
            )
        ).all()
        for pid, score in rows:
            review_scores.setdefault(pid, []).append(score)

    pois = [
        DiscoverPOI(
            id=p.id,
            name=p.name,
            category=p.category,
            description=p.description,
            latitude=p.latitude,
            longitude=p.longitude,
            photo_url=p.photo_url,
            entry_fee_dzd=p.entry_fee_dzd,
            average_score=_avg_score(review_scores.get(p.id, [])),
            total_reviews=len(review_scores.get(p.id, [])),
        )
        for p in pois_rows
    ]

    # Experiences
    exp_rows = (
        (
            await db.execute(
                select(Experience)
                .where(Experience.wilaya_id == wilaya_id, Experience.status == "active")
                .order_by(Experience.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    provider_ids = {e.provider_id for e in exp_rows}
    users = (
        (await db.execute(select(User).where(User.id.in_(provider_ids)))).scalars().all()
        if provider_ids
        else []
    )
    user_map = {u.id: u for u in users}

    experiences = [
        DiscoverExperience(
            id=e.id,
            title=e.title,
            category=e.category,
            description=e.description,
            price_dzd=e.price_dzd,
            duration_hours=e.duration_hours,
            provider_name=_display_name(user_map, e.provider_id),
            provider_avatar=_avatar_url(user_map, e.provider_id),
            meeting_point=e.meeting_point,
            photos=e.photos,
        )
        for e in exp_rows
    ]

    # Stays
    stay_rows = (
        (
            await db.execute(
                select(Stay)
                .where(Stay.wilaya_id == wilaya_id, Stay.is_active.is_(True))
                .order_by(Stay.price_per_night_dzd)
            )
        )
        .scalars()
        .all()
    )

    stay_provider_ids = {s.provider_id for s in stay_rows}
    stay_users = (
        (await db.execute(select(User).where(User.id.in_(stay_provider_ids)))).scalars().all()
        if stay_provider_ids
        else []
    )
    stay_user_map = {u.id: u for u in stay_users}

    stays = [
        DiscoverStay(
            id=s.id,
            name=s.name,
            property_type=s.property_type,
            description=s.description,
            price_per_night_dzd=s.price_per_night_dzd,
            amenities=s.amenities,
            photos=s.photos,
            latitude=s.latitude,
            longitude=s.longitude,
            max_guests=s.max_guests,
            provider_name=_display_name(stay_user_map, s.provider_id),
            provider_avatar=_avatar_url(stay_user_map, s.provider_id),
        )
        for s in stay_rows
    ]

    return DiscoverResponse(
        wilaya_id=wilaya_id,
        wilaya_name=wilaya.name_en,
        pois=pois,
        experiences=experiences,
        stays=stays,
    )


@router.get("/experiences/by-poi/{poi_id}")
async def experiences_by_poi(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    poi = await db.get(POI, poi_id)
    if not poi:
        raise NotFoundException(message="POI not found")

    exp_rows = (
        (
            await db.execute(
                select(Experience)
                .where(
                    Experience.wilaya_id == poi.wilaya_id,
                    Experience.status == "active",
                )
                .order_by(Experience.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    provider_ids = {e.provider_id for e in exp_rows}
    users = (
        (await db.execute(select(User).where(User.id.in_(provider_ids)))).scalars().all()
        if provider_ids
        else []
    )
    user_map = {u.id: u for u in users}

    results = []
    for e in exp_rows:
        matches = False
        if poi.name.lower() in (e.title + " " + (e.description or "")).lower():
            matches = True
        if not matches and poi.wilaya_id == e.wilaya_id:
            matches = True
        if matches:
            results.append(
                ExperienceFilterPOI(
                    experience_id=e.id,
                    title=e.title,
                    category=e.category,
                    price_dzd=e.price_dzd,
                    duration_hours=e.duration_hours,
                    provider_name=_display_name(user_map, e.provider_id),
                )
            )

    return results
