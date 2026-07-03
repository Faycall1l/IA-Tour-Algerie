import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.i18n import LocaleMiddleware, load_translations
from app.core.logging import setup_logging
from app.services.embeddings import EmbeddingService
from app.services.storage import StorageService
from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)

_legacy_routers: list = []


def _load_legacy_routers():
    try:
        from app.routers import admin_visa

        _legacy_routers.append(admin_visa.router)
    except Exception as exc:
        logger.warning("admin_visa router unavailable: %s", exc)
    try:
        from app.routers import whatsapp_bot

        _legacy_routers.append(whatsapp_bot.router)
    except Exception as exc:
        logger.warning("whatsapp_bot router unavailable: %s", exc)
    try:
        from app.routers import studio_media

        _legacy_routers.append(studio_media.router)
    except Exception as exc:
        logger.warning("studio_media router unavailable: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.debug)
    load_translations()
    app.state.storage = StorageService()
    app.state.embedder = EmbeddingService()
    app.state.vector_search = VectorSearchService(app.state.embedder)
    _load_legacy_routers()

    async def _index_existing_pois():
        try:
            from app.db.session import async_session_factory
            from app.models.poi import POI

            async with async_session_factory() as session:
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

    asyncio.ensure_future(_index_existing_pois())
    for r in _legacy_routers:
        app.include_router(r)
    Instrumentator().instrument(app).expose(app)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LocaleMiddleware)

app.include_router(v1_router)


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
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
