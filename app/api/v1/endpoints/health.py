import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.health import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Liveness + database connectivity probe. Returns 'ok' or 'degraded' with per-service status and latency.",
    responses={
        200: {"description": "API + database status"},
        422: {"description": "Validation error"},
    },
)
async def health_check(db: AsyncSession = Depends(get_db)):
    services = [ServiceStatus(name="api", status="ok")]

    t0 = time.monotonic()
    try:
        await db.execute(text("SELECT 1"))
        services.append(
            ServiceStatus(
                name="database",
                status="ok",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        )
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        services.append(ServiceStatus(name="database", status="error"))

    return HealthResponse(
        status="ok" if all(s.status == "ok" for s in services) else "degraded",
        version=settings.app_version,
        services=services,
    )
