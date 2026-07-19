import uuid

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.storage import StorageService
from app.services.transit_routing import TransitRoutingService
from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer
from app.services.twilio import TwilioService
from app.services.vector_search import VectorSearchService


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


async def get_provider_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in ("admin", "provider"):
        raise ForbiddenException(message="Admin or provider access required")
    return current_user


async def get_storage(request: Request) -> StorageService:
    return request.app.state.storage


async def get_vector_search(request: Request) -> VectorSearchService:
    return request.app.state.vector_search


async def get_trip_optimizer(request: Request) -> TripOptimizer:
    return request.app.state.trip_optimizer


async def get_trip_brief_generator(request: Request) -> TripBriefGenerator:
    return request.app.state.trip_brief_generator


async def get_twilio(request: Request) -> TwilioService:
    return request.app.state.twilio


async def get_coordinator_agent(request: Request):
    return getattr(request.app.state, "coordinator_agent", None)


async def get_transit_routing(request: Request) -> TransitRoutingService:
    return request.app.state.transit_routing
