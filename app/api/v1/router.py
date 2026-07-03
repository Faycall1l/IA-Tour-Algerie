from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, live, prices, wilayas

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(live.router)
router.include_router(prices.router)
router.include_router(wilayas.router)
