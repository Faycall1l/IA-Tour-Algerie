import logging
import uuid

from fastapi import APIRouter, Depends, Form, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.live_post import LivePost
from app.models.user import User
from app.schemas.live_post import LivePostFeed, LivePostRead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["Algeria Live"])


@router.post("/posts", response_model=LivePostRead, status_code=201)
async def create_post(
    caption: str | None = Form(None, max_length=500),
    wilaya_id: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    photo_url = "https://placehold.co/600x400?text=Algeria+Live"
    post = LivePost(
        user_id=current_user.id,
        photo_url=photo_url,
        caption=caption,
        wilaya_id=wilaya_id,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return LivePostRead.model_validate(post)


@router.get("/posts", response_model=LivePostFeed)
async def get_feed(
    wilaya_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(LivePost).order_by(LivePost.created_at.desc())

    if wilaya_id:
        query = query.where(LivePost.wilaya_id == wilaya_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    posts = result.scalars().all()

    return LivePostFeed(
        items=[LivePostRead.model_validate(p) for p in posts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/posts/{post_id}", response_model=LivePostRead)
async def get_post(post_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    post = await db.get(LivePost, post_id)
    if not post:
        raise NotFoundException(message="Post not found")
    return LivePostRead.model_validate(post)
