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

from app.agents.travel_agent import (
    create_events_agent,
    create_itinerary_agent,
    create_search_agent,
    create_transport_agent,
    create_travel_agent,
)
from app.api.v1.operation_ids import generate_unique_id_function
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.error_middleware import ErrorMiddleware
from app.core.i18n import LocaleMiddleware
from app.core.limiter import (
    METHOD_LIMITS,
    _rate_limit_exceeded_handler,
    check_rate_limit,
    limiter,
)
from app.core.logging import setup_logging
from app.services.embeddings import EmbeddingService
from app.services.poi_transit_router import PoiTransitRouter
from app.services.response_cache import ResponseCache
from app.services.storage import StorageService
from app.services.transit_routing import TransitRoutingService
from app.services.transport import TransportService
from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer
from app.services.twilio import TwilioService
from app.services.vector_search import (
    EXPERIENCES_COLLECTION,
    POIS_COLLECTION,
    VectorSearchService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.debug)
    app.state.transport = TransportService()
    app.state.transit_routing = TransitRoutingService()
    app.state.poi_transit_router = PoiTransitRouter(transit_routing=app.state.transit_routing)
    app.state.storage = StorageService()
    app.state.embedder = EmbeddingService()
    app.state.vector_search = VectorSearchService(app.state.embedder)
    app.state.trip_optimizer = TripOptimizer(transit_routing=app.state.transit_routing)
    app.state.trip_brief_generator = TripBriefGenerator(transport_service=app.state.transport)
    app.state.twilio = TwilioService()
    app.state.response_cache = ResponseCache(ttl=300)

    # Initialize Pydantic AI travel agents (vLLM)
    bu = settings.agent.vllm.base_url
    ak = settings.agent.vllm.api_key
    mn = settings.agent.vllm.model
    app.state.travel_agent = create_travel_agent(base_url=bu, api_key=ak, model_name=mn)
    app.state.itinerary_agent = create_itinerary_agent(base_url=bu, api_key=ak, model_name=mn)
    app.state.search_agent = create_search_agent(base_url=bu, api_key=ak, model_name=mn)
    app.state.transport_agent = create_transport_agent(base_url=bu, api_key=ak, model_name=mn)
    app.state.events_agent = create_events_agent(base_url=bu, api_key=ak, model_name=mn)
    if ak:
        logger.info("Pydantic AI agents initialized: %s @ %s", mn, bu)
    else:
        logger.warning("No vLLM API key set — agent endpoints will return 503")

    async def _index_existing_data():
        # Batched, idempotent startup index: only (re)builds a collection when
        # it has fewer points than the DB row count, so normal boots skip fast.
        # Incremental create/update/delete endpoints keep collections in sync.
        try:
            from sqlalchemy import func

            from app.db.session import async_session
            from app.models.experience import Experience
            from app.models.poi import POI

            async with async_session() as session:
                poi_count = (
                    await session.execute(select(func.count()).select_from(POI))
                ).scalar() or 0
                exp_count = (
                    await session.execute(select(func.count()).select_from(Experience))
                ).scalar() or 0
                pois = (await session.execute(select(POI))).scalars().all() if poi_count else []
                exps = (
                    (await session.execute(select(Experience))).scalars().all() if exp_count else []
                )

            def _run() -> None:
                vs = app.state.vector_search
                if not vs.client:
                    logger.info("Qdrant unavailable — vector search indexing skipped")
                    return
                if pois and vs.count(POIS_COLLECTION) < len(pois):
                    n = vs.index_pois_bulk(pois)
                    logger.info("Indexed %d POIs in Qdrant (batch)", n)
                elif pois:
                    logger.info(
                        "Qdrant POI index already populated (%d points), skipping",
                        vs.count(POIS_COLLECTION),
                    )
                if exps and vs.count(EXPERIENCES_COLLECTION) < len(exps):
                    n = vs.index_experiences_bulk(exps)
                    logger.info("Indexed %d experiences in Qdrant (batch)", n)
                elif exps:
                    logger.info(
                        "Qdrant experience index already populated (%d points), skipping",
                        vs.count(EXPERIENCES_COLLECTION),
                    )

            await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as exc:
            logger.warning("Failed to index existing data in Qdrant: %s", exc)

    asyncio.create_task(_index_existing_data())

    async def _warm_embedder():
        # Load the embedding model in the background so the first vector
        # search doesn't block ~25s on model load. Non-fatal if unavailable.
        try:
            await asyncio.get_running_loop().run_in_executor(None, app.state.embedder.warm)
        except Exception as exc:
            logger.warning("Embedding model warm-up failed: %s", exc)

    asyncio.create_task(_warm_embedder())
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "ATHAR — agentic travel guide for Algeria. Discover POIs, stays, "
        "experiences and artisans; plan trips; route with real transit "
        "schedules across all 58 wilayas."
    ),
    contact={
        "name": "ATHAR",
        "url": "https://github.com/Faycall1l",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "Admin", "description": "Administration endpoints (role-gated)."},
        {"name": "agents", "description": "AI travel agents with multi-turn memory."},
        {"name": "Artisans", "description": "Artisan shops and craft listings."},
        {"name": "Authentication", "description": "Passwordless OTP auth + sessions."},
        {"name": "Collections", "description": "User-curated POI collections."},
        {"name": "Discover", "description": "Aggregated per-wilaya content payloads."},
        {"name": "Events", "description": "Festivals and local events."},
        {"name": "Experiences", "description": "Tours, activities and cultural experiences."},
        {"name": "Favorites", "description": "User favorites."},
        {"name": "GeoJSON", "description": "GeoJSON feeds for map rendering."},
        {"name": "Health", "description": "Liveness and dependency probes."},
        {"name": "Points of Interest", "description": "POI catalog, search, routing."},
        {"name": "Recommendations", "description": "Recommended content."},
        {"name": "Search", "description": "Global and typed search."},
        {"name": "Stays", "description": "Hotels, guesthouses and hostels."},
        {"name": "Trip Dashboard", "description": "Trip planning and optimization."},
        {"name": "Users", "description": "User accounts and profiles."},
        {"name": "Wilayas", "description": "Wilaya reference data."},
        {"name": "transport", "description": "Transit routes, schedules and pricing."},
    ],
    lifespan=lifespan,
    # Deterministic, path-based operation ids so generated clients (dashboard
    # openapi-typescript, mobile openapi_flutter_gen) get clean method names
    # that survive function renames.
    generate_unique_id_function=generate_unique_id_function,
    # Interactive docs / OpenAPI schema are dev-only surface; exposing them
    # in production leaks the full API contract and attack surface.
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
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
# Host-header allowlist guards against DNS rebinding and Host-header
# injection; defaults to loopback only, override via ATHAR_ALLOWED_HOSTS.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts or ["localhost", "127.0.0.1"],
)

app.include_router(v1_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # API serves no HTML; default-src 'none' + frame-ancestors 'none'
    # (clickjacking) are safe and strictly scoped.
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    # HSTS only makes sense (and is only honored) over HTTPS — send it when
    # not in debug mode so any TLS-terminating proxy sets the pins.
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    path = request.url.path
    if "/api/v1/auth/" in path or "/api/v1/users/me" in path:
        response.headers["Cache-Control"] = "no-store"
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
        return FastResponse(
            content=body, status_code=status, media_type="application/json", headers=headers
        )

    response = await call_next(request)
    if response.status_code == 200:
        chunks = [chunk async for chunk in response.body_iterator]
        body_bytes = b"".join(chunks)
        from fastapi.responses import Response as FastResponse

        await cache.set(
            request.method,
            str(request.url.path),
            str(request.url.query),
            body_bytes.decode(),
            response.status_code,
            dict(response.headers),
        )
        return FastResponse(
            content=body_bytes,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )

    return response


@app.middleware("http")
async def method_based_rate_limit(request: Request, call_next):
    """Apply rate limits per HTTP method on API routes using sliding-window counter.
    Skipped when settings.debug is True or app.state.skip_rate_limit is set."""
    if settings.debug or getattr(request.app.state, "skip_rate_limit", False):
        return await call_next(request)
    if request.url.path.startswith("/api/v1/") and request.method in METHOD_LIMITS:
        ip = request.client.host if request.client else "unknown"
        allowed, limit, remaining = check_rate_limit(ip, request.method)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {request.method} requests. "
                    f"Limit: {limit} per {METHOD_LIMITS[request.method][1]}s",
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        return response
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
