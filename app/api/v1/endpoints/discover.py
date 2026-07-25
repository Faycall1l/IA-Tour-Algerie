import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundException
from app.models.artisan import Artisan
from app.models.experience import Experience
from app.models.poi import POI
from app.models.stay import Stay
from app.models.user import User
from app.models.wilaya import Wilaya

CATEGORY_ORDER = {
    "museum": 1, "cultural": 2, "historical": 3, "natural": 4,
    "beach": 5, "park": 6, "mountain": 7, "market": 8,
    "religious": 9, "restaurant": 10, "cafe": 11, "other": 12,
}


def _avg_score(scores: list[int]) -> float | None:
    return round(sum(scores) / len(scores), 1) if scores else None


def _display_name(user_map: dict, user_id: uuid.UUID) -> str | None:
    u = user_map.get(user_id)
    return u.display_name if u else None


def _avatar_url(user_map: dict, user_id: uuid.UUID) -> str | None:
    u = user_map.get(user_id)
    return u.avatar_url if u else None


def _wilaya_name(w: Wilaya) -> str:
    return w.name_en or w.name_fr or w.name_ar or ""


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


class DiscoverArtisan(BaseModel):
    id: uuid.UUID
    name: str
    craft_type: str
    description: str | None
    latitude: float | None
    longitude: float | None
    address: str | None
    commune: str | None
    photos: list[str] | None
    years_experience: int | None
    specializations: list[str] | None
    accepts_visitors: bool
    is_verified: bool
    user_name: str | None = None


class DiscoverResponse(BaseModel):
    wilaya_id: int
    wilaya_name: str
    pois: list[DiscoverPOI]
    experiences: list[DiscoverExperience]
    stays: list[DiscoverStay]
    artisans: list[DiscoverArtisan]


class WilayaSummary(BaseModel):
    id: int
    name: str
    description: str | None = None
    total_pois: int = 0
    total_featured: int = 0
    total_experiences: int = 0
    total_stays: int = 0
    total_artisans: int = 0
    top_categories: list[str] = []
    highlight_poi: str | None = None
    highlight_poi_photo: str | None = None
    highlight_category: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class GuidePOI(BaseModel):
    id: uuid.UUID
    name: str
    name_ar: str | None = None
    category: str
    subtype: str | None = None
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_urls: list[str] | None = None
    is_featured: bool = False
    entry_fee_dzd: float | None = None
    price_level: str | None = None
    suggested_duration_min: int | None = None
    average_score: float | None = None
    total_reviews: int = 0
    accessibility_score: int | None = None
    combined_score: float | None = None
    nearest_station_name: str | None = None
    distance_to_station_km: float | None = None
    walking_time_min: int | None = None
    modes_nearby: list[str] | None = None


class GuideCategory(BaseModel):
    count: int
    pois: list[GuidePOI]


class GuideResponse(BaseModel):
    wilaya_id: int
    wilaya_name: str
    description: str | None = None
    total_pois: int
    total_featured: int
    featured_pois: list[GuidePOI]
    categories: dict[str, GuideCategory]
    experiences: list[DiscoverExperience]
    stays: list[DiscoverStay]


class ExperienceFilterPOI(BaseModel):
    experience_id: uuid.UUID
    title: str
    category: str
    price_dzd: float | None
    duration_hours: float | None
    provider_name: str | None


@router.get("/wilayas", response_model=list[WilayaSummary])
async def list_wilayas(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Wilaya).order_by(Wilaya.id)
    )
    wilayas = result.scalars().all()

    summaries = []
    for w in wilayas:
        poi_rows = (
            await db.execute(
                select(POI.id, POI.is_featured, POI.category, POI.name, POI.photo_url, POI.photo_urls, POI.getting_there)
                .where(POI.wilaya_id == w.id)
                .order_by(
                    POI.is_featured.desc().nullslast(),
                    text("(getting_there->>'combined_score')::float DESC NULLS LAST"),
                )
            )
        ).all()

        total_pois = len(poi_rows)
        featured_count = sum(1 for r in poi_rows if r.is_featured)

        # Top categories
        cat_counts: dict[str, int] = {}
        for r in poi_rows:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        top_cats = sorted(cat_counts, key=lambda c: cat_counts[c], reverse=True)[:5]

        # Highlight: first featured POI with a photo
        highlight_poi = None
        highlight_photo = None
        highlight_cat = None
        for r in poi_rows:
            if r.is_featured:
                name_str = r.name or ""
                if len(name_str) > 0:
                    highlight_poi = name_str
                    highlight_cat = r.category
                    photos = r.photo_urls or []
                    if r.photo_url and r.photo_url not in photos:
                        photos = [r.photo_url] + (photos or [])
                    highlight_photo = next((u for u in photos if u and len(u) > 5), None)
                    break
        if not highlight_poi and poi_rows:
            r = poi_rows[0]
            highlight_poi = r.name or None
            highlight_cat = r.category

        # Experience and stay counts
        exp_count = await db.scalar(
            select(func.count(Experience.id)).where(
                Experience.wilaya_id == w.id, Experience.status == "active"
            )
        )

        stay_count = await db.scalar(
            select(func.count(Stay.id)).where(
                Stay.wilaya_id == w.id, Stay.is_active.is_(True)
            )
        )

        artisan_count = await db.scalar(
            select(func.count(Artisan.id)).where(Artisan.wilaya_id == w.id)
        )

        summaries.append(WilayaSummary(
            id=w.id,
            name=_wilaya_name(w),
            description=w.description,
            total_pois=total_pois,
            total_featured=featured_count,
            total_experiences=exp_count or 0,
            total_stays=stay_count or 0,
            total_artisans=artisan_count or 0,
            top_categories=top_cats,
            highlight_poi=highlight_poi,
            highlight_poi_photo=highlight_photo,
            highlight_category=highlight_cat,
            latitude=w.latitude,
            longitude=w.longitude,
        ))

    return summaries


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
            average_score=None,
            total_reviews=0,
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

    # Artisans
    artisan_rows = (
        (await db.execute(
            select(Artisan).where(Artisan.wilaya_id == wilaya_id).order_by(Artisan.name)
        ))
        .scalars()
        .all()
    )

    artisan_user_ids = {a.user_id for a in artisan_rows}
    artisan_users = (
        (await db.execute(select(User).where(User.id.in_(artisan_user_ids)))).scalars().all()
        if artisan_user_ids
        else []
    )
    artisan_user_map = {u.id: u for u in artisan_users}

    artisans = [
        DiscoverArtisan(
            id=a.id,
            name=a.name,
            craft_type=a.craft_type,
            description=a.description,
            latitude=a.latitude,
            longitude=a.longitude,
            address=a.address,
            commune=a.commune,
            photos=a.photos,
            years_experience=a.years_experience,
            specializations=a.specializations,
            accepts_visitors=a.accepts_visitors,
            is_verified=a.is_verified,
            user_name=_display_name(artisan_user_map, a.user_id),
        )
        for a in artisan_rows
    ]

    return DiscoverResponse(
        wilaya_id=wilaya_id,
        wilaya_name=wilaya.name_en,
        pois=pois,
        experiences=experiences,
        stays=stays,
        artisans=artisans,
    )
@router.get("/wilayas/{wilaya_id}/guide", response_model=GuideResponse)
async def wilaya_guide(
    wilaya_id: int,
    top_per_category: int = Query(10, alias="top"),
    db: AsyncSession = Depends(get_db),
):
    wilaya = await db.get(Wilaya, wilaya_id)
    if not wilaya:
        raise NotFoundException(message="Wilaya not found")

    # Fetch all POIs for this wilaya with getting_there data, ordered by score
    result = await db.execute(
        select(POI)
        .where(POI.wilaya_id == wilaya_id)
        .order_by(
            POI.is_featured.desc().nullslast(),
            text("(getting_there->>'combined_score')::float DESC NULLS LAST"),
            POI.name,
        )
    )
    all_pois = result.scalars().all()

    if not all_pois:
        return GuideResponse(
            wilaya_id=wilaya_id,
            wilaya_name=_wilaya_name(wilaya),
            total_pois=0,
            total_featured=0,
            featured_pois=[],
            categories={},
            experiences=[],
            stays=[],
        )

    def build_guide_poi(p: POI) -> GuidePOI:
        gt = p.getting_there or {}
        return GuidePOI(
            id=p.id,
            name=p.name,
            name_ar=p.name_ar,
            category=p.category,
            subtype=p.subtype,
            description=p.description,
            latitude=p.latitude,
            longitude=p.longitude,
            photo_urls=[u for u in (p.photo_urls or []) if u] if p.photo_urls else ([p.photo_url] if p.photo_url else None),
            is_featured=p.is_featured or False,
            entry_fee_dzd=p.entry_fee_dzd,
            price_level=p.price_level,
            suggested_duration_min=p.suggested_duration_min,
            average_score=None,
            total_reviews=0,
            accessibility_score=gt.get("accessibility_score"),
            combined_score=gt.get("combined_score"),
            nearest_station_name=gt.get("nearest_station_name"),
            distance_to_station_km=gt.get("distance_km"),
            walking_time_min=gt.get("walking_time_min"),
            modes_nearby=gt.get("modes_nearby"),
        )

    # Separate featured from non-featured
    featured = [build_guide_poi(p) for p in all_pois if p.is_featured]

    # Group by category, capped at top_per_category
    categories: dict[str, list[GuidePOI]] = {}
    for p in all_pois:
        cat = p.category
        if cat not in categories:
            categories[cat] = []
        if len(categories[cat]) < top_per_category:
            categories[cat].append(build_guide_poi(p))

    # Sort categories by importance
    sorted_categories: dict[str, GuideCategory] = {}
    for cat in sorted(categories, key=lambda c: CATEGORY_ORDER.get(c, 99)):
        sorted_categories[cat] = GuideCategory(
            count=sum(1 for p in all_pois if p.category == cat),
            pois=categories[cat],
        )

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

    return GuideResponse(
        wilaya_id=wilaya_id,
        wilaya_name=_wilaya_name(wilaya),
        description=wilaya.description,
        total_pois=len(all_pois),
        total_featured=len(featured),
        featured_pois=featured,
        categories=sorted_categories,
        experiences=experiences,
        stays=stays,
    )


@router.get("/experiences/by-poi/{poi_id}", response_model=list[ExperienceFilterPOI])
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
