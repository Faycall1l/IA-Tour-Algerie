import logging
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage, get_vector_search
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.experience import EXPERIENCE_CATEGORIES, Experience
from app.models.provider_profile import PROVIDER_TYPES
from app.models.user import User
from app.models.wilaya import Wilaya
from app.schemas.experience import (
    ExperienceCreate,
    ExperienceDetail,
    ExperienceFeed,
    ExperienceRead,
    ExperienceUpdate,
)
from app.services.storage import StorageService
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experiences", tags=["Experiences"])


def _can_manage(current_user: User, experience: Experience) -> bool:
    return current_user.id == experience.provider_id or current_user.role == "admin"


@router.post("", response_model=ExperienceRead, status_code=201)
async def create_experience(
    body: ExperienceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    if current_user.role not in PROVIDER_TYPES:
        raise BadRequestException(message="Only providers (guide/agency/hotel) can add experiences")

    wilaya = await db.get(Wilaya, body.wilaya_id)
    if not wilaya:
        raise NotFoundException(message=f"Wilaya {body.wilaya_id} not found")

    experience = Experience(provider_id=current_user.id, **body.model_dump())
    db.add(experience)
    await db.commit()
    await db.refresh(experience)

    vector_search.index_experience(experience)

    return ExperienceRead.model_validate(experience)


@router.get("", response_model=ExperienceFeed)
async def list_experiences(
    wilaya_id: int | None = Query(None, ge=1, le=58),
    category: str | None = Query(None, pattern=f"^({'|'.join(EXPERIENCE_CATEGORIES)})$"),
    provider_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None, pattern="^(active|draft|cancelled)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Experience)

    if wilaya_id:
        query = query.where(Experience.wilaya_id == wilaya_id)
    if category:
        query = query.where(Experience.category == category)
    if provider_id:
        query = query.where(Experience.provider_id == provider_id)
    if status:
        query = query.where(Experience.status == status)
    else:
        query = query.where(Experience.status == "active")

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(Experience.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    result = await db.execute(query)
    items = [ExperienceRead.model_validate(e) for e in result.scalars().all()]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return ExperienceFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/search", response_model=ExperienceFeed)
async def search_experiences(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    ids = vector_search.search_experiences(q, limit=limit)
    experiences: list[Experience] = []
    if ids:
        seen = set()
        for eid in ids:
            if eid in seen:
                continue
            seen.add(eid)
            exp = await db.get(Experience, eid)
            if exp and exp.status == "active":
                experiences.append(exp)

    items = [ExperienceRead.model_validate(e) for e in experiences]
    total = len(items)
    return ExperienceFeed(
        items=items,
        total=total,
        page=1,
        page_size=total or 1,
        total_pages=1,
        has_prev=False,
        has_next=False,
    )


@router.get("/{experience_id}", response_model=ExperienceDetail)
async def get_experience(experience_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    experience = await db.get(Experience, experience_id)
    if not experience:
        raise NotFoundException(message="Experience not found")

    provider = await db.get(User, experience.provider_id)
    return ExperienceDetail(
        experience=ExperienceRead.model_validate(experience),
        provider_name=provider.display_name or provider.phone if provider else None,
        provider_avatar=provider.avatar_url if provider else None,
        provider_role=provider.role if provider else None,
    )


@router.put("/{experience_id}", response_model=ExperienceRead)
async def update_experience(
    experience_id: uuid.UUID,
    body: ExperienceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    experience = await db.get(Experience, experience_id)
    if not experience:
        raise NotFoundException(message="Experience not found")
    if not _can_manage(current_user, experience):
        raise ForbiddenException(message="You can only edit your own experiences")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(experience, field, value)

    await db.commit()
    await db.refresh(experience)

    vector_search.index_experience(experience)
    return ExperienceRead.model_validate(experience)


@router.delete("/{experience_id}", status_code=204)
async def delete_experience(
    experience_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vector_search: VectorSearchService = Depends(get_vector_search),
):
    experience = await db.get(Experience, experience_id)
    if not experience:
        raise NotFoundException(message="Experience not found")
    if not _can_manage(current_user, experience):
        raise ForbiddenException(message="You can only delete your own experiences")

    await db.delete(experience)
    await db.commit()
    vector_search.delete_experience(experience_id)


@router.post("/{experience_id}/photos", response_model=ExperienceRead)
async def upload_experience_photos(
    experience_id: uuid.UUID,
    photos: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    experience = await db.get(Experience, experience_id)
    if not experience:
        raise NotFoundException(message="Experience not found")
    if not _can_manage(current_user, experience):
        raise ForbiddenException(message="You can only edit your own experiences")

    urls = []
    for photo in photos:
        url = await storage.upload(photo, folder="experiences")
        urls.append(url)

    existing = experience.photos or []
    experience.photos = existing + urls
    await db.commit()
    await db.refresh(experience)

    return ExperienceRead.model_validate(experience)
