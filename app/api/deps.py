import uuid

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.core.security import decode_token
from app.models.user import User


async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException(message="Missing or invalid token")
    token = authorization.split(" ")[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise UnauthorizedException(message="Invalid or expired token")
    if payload.get("type") != "access":
        raise UnauthorizedException(message="Invalid token type")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        raise UnauthorizedException(message="User not found")
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise ForbiddenException(message="Admin access required")
    return current_user
