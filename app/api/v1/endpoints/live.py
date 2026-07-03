import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_storage
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.live_post import LivePost
from app.models.user import User
from app.schemas.live_post import LivePostFeed, LivePostRead
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["Algeria Live"])


def _build_filters(
    wilaya_id: int | None,
    user_id: uuid.UUID | None,
) -> list:
    conds = []
    if wilaya_id is not None:
        conds.append(LivePost.wilaya_id == wilaya_id)
    if user_id is not None:
        conds.append(LivePost.user_id == user_id)
    return conds


@router.post("/posts", response_model=LivePostRead, status_code=201)
async def create_post(
    photo: UploadFile = File(...),
    caption: str | None = Form(None, max_length=500),
    wilaya_id: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    photo_url = await storage.upload(photo, folder="live")
    post = LivePost(
        user_id=current_user.id,
        photo_url=photo_url,
        caption=caption,
        wilaya_id=wilaya_id,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return LivePostRead(
        **LivePostRead.model_validate(post).model_dump(),
        user_name=current_user.display_name or current_user.phone,
        user_avatar=current_user.avatar_url,
    )


@router.get("/posts", response_model=LivePostFeed)
async def get_feed(
    wilaya_id: int | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    filters = _build_filters(wilaya_id, user_id)

    count_query = select(func.count()).select_from(select(LivePost).where(*filters).subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(LivePost, User.display_name, User.phone, User.avatar_url)
        .join(User, LivePost.user_id == User.id)
        .where(*filters)
        .order_by(LivePost.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    rows = result.all()

    items = []
    for post, display_name, phone, avatar_url in rows:
        items.append(
            LivePostRead(
                **LivePostRead.model_validate(post).model_dump(),
                user_name=display_name or phone,
                user_avatar=avatar_url,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return LivePostFeed(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )


@router.get("/posts/{post_id}", response_model=LivePostRead)
async def get_post(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    query = (
        select(LivePost, User.display_name, User.phone, User.avatar_url)
        .join(User, LivePost.user_id == User.id)
        .where(LivePost.id == post_id)
    )
    result = await db.execute(query)
    row = result.one_or_none()
    if not row:
        raise NotFoundException(message="Post not found")

    post, display_name, phone, avatar_url = row
    return LivePostRead(
        **LivePostRead.model_validate(post).model_dump(),
        user_name=display_name or phone,
        user_avatar=avatar_url,
    )


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(LivePost, post_id)
    if not post:
        raise NotFoundException(message="Post not found")
    if post.user_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete your own posts")
    await db.delete(post)
    await db.commit()
