import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.favorite import Favorite
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoriteFeed, FavoriteRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.post(
    "",
    response_model=FavoriteRead,
    status_code=201,
    summary="Add a favorite",
    description="Favorite an entity (poi, experience, or stay) by entity_type + entity_id. Returns 404-style error if already favorited.",  # noqa: E501
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Already in favorites"},
        422: {"description": "Validation error"},
    },
)
async def add_favorite(
    body: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Favorite).where(
            Favorite.user_id == current_user.id,
            Favorite.entity_type == body.entity_type,
            Favorite.entity_id == body.entity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise NotFoundException(message="Already in favorites")

    fav = Favorite(user_id=current_user.id, entity_type=body.entity_type, entity_id=body.entity_id)
    db.add(fav)
    await db.commit()
    await db.refresh(fav)
    return FavoriteRead.model_validate(fav)


@router.get(
    "",
    response_model=FavoriteFeed,
    summary="List favorites",
    description="The authenticated user's favorites, newest first. Optionally filtered by entity_type.",  # noqa: E501
    responses={
        401: {"description": "Authentication required"},
        200: {"description": "Favorite feed"},
    },
)
async def list_favorites(
    entity_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Favorite).where(Favorite.user_id == current_user.id)
    if entity_type:
        query = query.where(Favorite.entity_type == entity_type)
    query = query.order_by(Favorite.created_at.desc())

    result = await db.execute(query)
    items = [FavoriteRead.model_validate(f) for f in result.scalars().all()]
    return FavoriteFeed(items=items, total=len(items))


@router.delete(
    "/{favorite_id}",
    status_code=204,
    summary="Remove a favorite",
    description="Unfavorite an entity. Only the owning user can remove.",
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Favorite not found"},
    },
)
async def remove_favorite(
    favorite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fav = await db.get(Favorite, favorite_id)
    if not fav or fav.user_id != current_user.id:
        raise NotFoundException(message="Favorite not found")
    await db.delete(fav)
    await db.commit()
