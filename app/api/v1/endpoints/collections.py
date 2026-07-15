import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.collection import Collection, CollectionItem
from app.models.user import User
from app.schemas.collection import (
    CollectionBrief,
    CollectionCreate,
    CollectionFeed,
    CollectionItemBatchCreate,
    CollectionItemCreate,
    CollectionItemRead,
    CollectionRead,
    CollectionUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collections", tags=["Collections"])


async def _get_user_collection(collection_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Collection:
    result = await db.execute(
        select(Collection).where(Collection.id == collection_id, Collection.user_id == user_id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise NotFoundException(message="Collection not found")
    return c


def _brief(c: Collection) -> CollectionBrief:
    return CollectionBrief(
        id=c.id, name=c.name, description=c.description,
        is_public=c.is_public, item_count=len(c.items) if c.items else 0,
        created_at=c.created_at,
    )


# ── CRUD ──

@router.get("", response_model=CollectionFeed)
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .options(selectinload(Collection.items))
        .order_by(Collection.created_at.desc())
    )
    collections = result.scalars().all()
    return CollectionFeed(items=[_brief(c) for c in collections], total=len(collections))


@router.post("", response_model=CollectionRead, status_code=201)
async def create_collection(
    body: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = Collection(user_id=current_user.id, name=body.name, description=body.description, is_public=body.is_public)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return CollectionRead(
        id=c.id, user_id=c.user_id, name=c.name, description=c.description,
        is_public=c.is_public, item_count=0, items=[],
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.get("/{collection_id}", response_model=CollectionRead)
async def get_collection(
    collection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_user_collection(collection_id, current_user.id, db)
    # Reload with items eagerly
    result = await db.execute(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(selectinload(Collection.items))
    )
    c = result.scalar_one()
    return CollectionRead(
        id=c.id, user_id=c.user_id, name=c.name, description=c.description,
        is_public=c.is_public,
        item_count=len(c.items),
        items=[
            CollectionItemRead(
                id=i.id, entity_type=i.entity_type, entity_id=i.entity_id,
                notes=i.notes, sort_order=i.sort_order, created_at=i.created_at,
            )
            for i in sorted(c.items, key=lambda x: (x.sort_order, x.created_at))
        ],
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.put("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_user_collection(collection_id, current_user.id, db)
    if body.name is not None:
        c.name = body.name
    if body.description is not None:
        c.description = body.description
    if body.is_public is not None:
        c.is_public = body.is_public
    c.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(c)

    return CollectionRead(
        id=c.id, user_id=c.user_id, name=c.name, description=c.description,
        is_public=c.is_public, item_count=len(c.items) if c.items else 0,
        items=[], created_at=c.created_at, updated_at=c.updated_at,
    )


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_user_collection(collection_id, current_user.id, db)
    await db.delete(c)
    await db.commit()


# ── Items ──

@router.post("/{collection_id}/items", response_model=list[CollectionItemRead], status_code=201)
async def add_items(
    collection_id: uuid.UUID,
    body: CollectionItemBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_user_collection(collection_id, current_user.id, db)

    if not body.items:
        raise BadRequestException(message="At least one item required")

    created = []
    for entry in body.items:
        # Check for duplicates
        existing = await db.execute(
            select(CollectionItem).where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.entity_type == entry.entity_type,
                CollectionItem.entity_id == entry.entity_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        item = CollectionItem(
            collection_id=collection_id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            notes=entry.notes,
            sort_order=entry.sort_order,
            created_at=datetime.utcnow(),
        )
        db.add(item)
        created.append(item)

    if created:
        await db.commit()
        for item in created:
            await db.refresh(item)

    return [
        CollectionItemRead(
            id=i.id, entity_type=i.entity_type, entity_id=i.entity_id,
            notes=i.notes, sort_order=i.sort_order, created_at=i.created_at,
        )
        for i in created
    ]


@router.delete("/{collection_id}/items/{item_id}", status_code=204)
async def remove_item(
    collection_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c = await _get_user_collection(collection_id, current_user.id, db)
    result = await db.execute(
        select(CollectionItem).where(
            CollectionItem.id == item_id,
            CollectionItem.collection_id == collection_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise NotFoundException(message="Item not found in collection")

    await db.delete(item)
    await db.commit()
