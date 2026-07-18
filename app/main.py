import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.error_middleware import ErrorMiddleware
from app.core.i18n import LocaleMiddleware, load_translations
from app.core.limiter import (
    METHOD_LIMITS,
    _rate_limit_exceeded_handler,
    check_rate_limit,
    limiter,
)
from app.core.logging import setup_logging
from app.agents.travel_agent import (
    create_itinerary_agent,
    create_search_agent,
    create_travel_agent,
)
from app.services.agent.agents.coordinator import get_coordinator
from app.services.embeddings import EmbeddingService
from app.services.response_cache import ResponseCache
from app.services.storage import StorageService
from app.services.transit_routing import TransitRoutingService
from app.services.transport import TransportService
from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer
from app.services.twilio import TwilioService
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)

_legacy_routers: list = []


def _load_legacy_routers():
    try:
        from app.api.v1.endpoints import admin_visa

        _legacy_routers.append(admin_visa.router)
    except Exception as exc:
        logger.warning("admin_visa router unavailable: %s", exc)
    try:
        from app.api.v1.endpoints import whatsapp_bot

        _legacy_routers.append(whatsapp_bot.router)
    except Exception as exc:
        logger.warning("whatsapp_bot router unavailable: %s", exc)
    try:
        from app.api.v1.endpoints import studio_media

        _legacy_routers.append(studio_media.router)
    except Exception as exc:
        logger.warning("studio_media router unavailable: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.debug)
    load_translations()
    app.state.transport = TransportService()
    app.state.transit_routing = TransitRoutingService()
    app.state.storage = StorageService()
    app.state.embedder = EmbeddingService()
    app.state.vector_search = VectorSearchService(app.state.embedder)
    app.state.trip_optimizer = TripOptimizer(transit_routing=app.state.transit_routing)
    app.state.trip_brief_generator = TripBriefGenerator(transport_service=app.state.transport)
    app.state.twilio = TwilioService()
    app.state.response_cache = ResponseCache(ttl=300)
    if settings.agent.enabled:
        coordinator = get_coordinator()
        app.state.coordinator_agent = coordinator
        if coordinator:
            logger.info("Agent layer initialized (enabled=%s)", settings.agent.enabled)
        else:
            logger.warning("Agent layer enabled but failed to initialize")

    # Initialize Pydantic AI travel agents
    ak = settings.agent.openrouter_api_key
    mn = settings.agent.openrouter_model
    app.state.travel_agent = create_travel_agent(api_key=ak, model_name=mn)
    app.state.itinerary_agent = create_itinerary_agent(api_key=ak, model_name=mn)
    app.state.search_agent = create_search_agent(api_key=ak, model_name=mn)
    if ak:
        logger.info("Pydantic AI agents initialized with model=%s", mn)
    else:
        logger.warning("No OPENROUTER_API_KEY set — agent endpoints will return 503")
    _load_legacy_routers()

    async def _index_existing_pois():
        try:
            from app.db.session import async_session
            from app.models.poi import POI

            async with async_session() as session:
                pois = (await session.execute(select(POI))).scalars().all()
            if pois:
                loop = asyncio.get_running_loop()

                def _index() -> None:
                    for p in pois:
                        app.state.vector_search.index_poi(p)

                await loop.run_in_executor(None, _index)
                logger.info("Indexed %d existing POIs in Qdrant", len(pois))
            else:
                logger.info("No existing POIs to index")
        except Exception as exc:
            logger.warning("Failed to index existing POIs: %s", exc)

    async def _index_existing_experiences():
        try:
            from app.db.session import async_session
            from app.models.experience import Experience

            async with async_session() as session:
                exps = (await session.execute(select(Experience))).scalars().all()
            if exps:
                loop = asyncio.get_running_loop()

                def _idx() -> None:
                    for e in exps:
                        app.state.vector_search.index_experience(e)

                await loop.run_in_executor(None, _idx)
                logger.info("Indexed %d existing experiences in Qdrant", len(exps))
        except Exception as exc:
            logger.warning("Failed to index existing experiences: %s", exc)

    asyncio.create_task(_index_existing_pois())
    asyncio.create_task(_index_existing_experiences())
    for r in _legacy_routers:
        app.include_router(r)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    max_age=3600,
)
app.add_middleware(ErrorMiddleware)
app.add_middleware(LocaleMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts or ["*"])

app.include_router(v1_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.middleware("http")
async def cache_get_responses(request: Request, call_next):
    """Cache GET responses for read-heavy list endpoints (300s TTL).
    Skips authenticated requests, search endpoints, and non-200 responses."""
    cache = getattr(request.app.state, "response_cache", None)
    if (
        cache is None
        or request.method != "GET"
        or request.headers.get("Authorization")
        or not request.url.path.startswith("/api/v1/")
        or "search" in request.url.path
    ):
        return await call_next(request)

    cached = await cache.get(request.method, str(request.url.path), str(request.url.query))
    if cached:
        from fastapi.responses import Response as FastResponse
        body, status, headers = cached
        return FastResponse(content=body, status_code=status, media_type="application/json", headers=headers)

    response = await call_next(request)
    if response.status_code == 200:
        chunks = [chunk async for chunk in response.body_iterator]
        body_bytes = b"".join(chunks)
        from fastapi.responses import Response as FastResponse
        await cache.set(request.method, str(request.url.path), str(request.url.query), body_bytes.decode(), response.status_code, dict(response.headers))
        return FastResponse(content=body_bytes, status_code=response.status_code, media_type=response.media_type, headers=dict(response.headers))

    return response


@app.middleware("http")
async def method_based_rate_limit(request: Request, call_next):
    """Apply rate limits per HTTP method on API routes using sliding-window counter.
    Skipped when settings.debug is True or app.state.skip_rate_limit is set."""
    if settings.debug or getattr(request.app.state, "skip_rate_limit", False):
        return await call_next(request)
    if request.url.path.startswith("/api/v1/") and request.method in METHOD_LIMITS:
        ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(ip, request.method):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {request.method} requests. "
                    f"Limit: {METHOD_LIMITS[request.method][0]} per {METHOD_LIMITS[request.method][1]}s",
                },
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
    from app.core.exceptions import AppError

    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred"},
    )
