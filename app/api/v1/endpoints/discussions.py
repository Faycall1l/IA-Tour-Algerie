import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.discussion import DISCUSSION_ENTITY_TYPES, DiscussionPost, DiscussionThread
from app.models.user import User
from app.schemas.discussion import (
    DiscussionPostCreate,
    DiscussionPostRead,
    DiscussionThreadCreate,
    DiscussionThreadDetail,
    DiscussionThreadFeed,
    DiscussionThreadRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discussions", tags=["Discussions"])


async def _build_thread_read(thread: DiscussionThread, db: AsyncSession) -> DiscussionThreadRead:
    count_q = select(func.count()).select_from(
        select(DiscussionPost).where(DiscussionPost.thread_id == thread.id).subquery()
    )
    post_count = (await db.execute(count_q)).scalar() or 0

    last_q = (
        select(DiscussionPost.created_at)
        .where(DiscussionPost.thread_id == thread.id)
        .order_by(DiscussionPost.created_at.desc())
        .limit(1)
    )
    last = (await db.execute(last_q)).scalar()

    return DiscussionThreadRead(
        id=thread.id,
        entity_type=thread.entity_type,
        entity_id=thread.entity_id,
        title=thread.title,
        created_by=thread.created_by,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        post_count=post_count,
        last_post_at=last,
    )


async def _build_post_read(post: DiscussionPost, db: AsyncSession) -> DiscussionPostRead:
    from app.models.user import User as UserModel

    user = await db.get(UserModel, post.author_id)
    return DiscussionPostRead(
        id=post.id,
        thread_id=post.thread_id,
        parent_id=post.parent_id,
        author_id=post.author_id,
        author_name=user.display_name or user.phone if user else None,
        content=post.content,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


@router.post("", response_model=DiscussionThreadRead, status_code=201)
async def create_thread(
    body: DiscussionThreadCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = DiscussionThread(
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        title=body.title,
        created_by=current_user.id,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return await _build_thread_read(thread, db)


@router.get("", response_model=DiscussionThreadFeed)
async def list_threads(
    entity_type: str = Query(..., pattern=f"^({'|'.join(DISCUSSION_ENTITY_TYPES)})$"),
    entity_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    query = select(DiscussionThread).where(
        DiscussionThread.entity_type == entity_type,
        DiscussionThread.entity_id == entity_id,
    ).order_by(DiscussionThread.created_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query)
    threads = result.scalars().all()

    items = [await _build_thread_read(t, db) for t in threads]
    return DiscussionThreadFeed(items=items, total=total)


@router.get("/{thread_id}", response_model=DiscussionThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if not thread:
        raise NotFoundException(message="Discussion thread not found")

    posts_q = select(DiscussionPost).where(
        DiscussionPost.thread_id == thread_id
    ).order_by(DiscussionPost.created_at)
    posts_result = await db.execute(posts_q)
    posts_raw = posts_result.scalars().all()

    posts = [await _build_post_read(p, db) for p in posts_raw]
    thread_read = await _build_thread_read(thread, db)

    return DiscussionThreadDetail(thread=thread_read, posts=posts)


@router.post("/{thread_id}/posts", response_model=DiscussionPostRead, status_code=201)
async def create_post(
    thread_id: uuid.UUID,
    body: DiscussionPostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if not thread:
        raise NotFoundException(message="Discussion thread not found")

    if body.parent_id:
        parent = await db.get(DiscussionPost, body.parent_id)
        if not parent or parent.thread_id != thread_id:
            raise NotFoundException(message="Parent post not found in this thread")

    post = DiscussionPost(
        thread_id=thread_id,
        parent_id=body.parent_id,
        author_id=current_user.id,
        content=body.content,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return await _build_post_read(post, db)


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    thread = await db.get(DiscussionThread, thread_id)
    if not thread:
        raise NotFoundException(message="Discussion thread not found")
    if thread.created_by != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete your own threads")
    await db.delete(thread)
    await db.commit()


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(DiscussionPost, post_id)
    if not post:
        raise NotFoundException(message="Post not found")
    if post.author_id != current_user.id and current_user.role != "admin":
        raise ForbiddenException(message="You can only delete your own posts")
    await db.delete(post)
    await db.commit()
