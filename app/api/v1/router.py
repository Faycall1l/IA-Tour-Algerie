from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    bookings,
    experiences,
    health,
    live,
    notifications,
    pois,
    prices,
    reviews,
    users,
    wilayas,
)

router = APIRouter(prefix="/api/v1")
router.include_router(admin.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(live.router)
router.include_router(pois.router)
router.include_router(prices.router)
router.include_router(reviews.router)
router.include_router(users.router)
router.include_router(wilayas.router)
router.include_router(experiences.router)
router.include_router(bookings.router)
router.include_router(notifications.router)
