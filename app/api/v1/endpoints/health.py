from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db
from app.core.config import settings
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    services = [
        ServiceStatus(name="api", status="ok"),
    ]

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        services=services,
    )
