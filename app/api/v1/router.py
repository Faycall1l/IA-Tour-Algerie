from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    agents,
    auth,
    bookings,
    circuits,
    collections,
    discover,
    events,
    experiences,
    favorites,
    geojson,
    health,
    discussions,
    live,
    notifications,
    pois,
    price_calendar,
    prices,
    reviews,
    search,
    stays,
    transport,
    trips,
    users,
    wilayas,
)

router = APIRouter(prefix="/api/v1")
router.include_router(admin.router)
router.include_router(agents.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(discussions.router)
router.include_router(discover.router)
router.include_router(events.router)
router.include_router(live.router)
router.include_router(pois.router)
router.include_router(price_calendar.router)
router.include_router(prices.router)
router.include_router(reviews.router)
router.include_router(users.router)
router.include_router(wilayas.router)
router.include_router(experiences.router)
router.include_router(bookings.router)
router.include_router(circuits.router)
router.include_router(notifications.router)
router.include_router(stays.router)
router.include_router(transport.router)
router.include_router(trips.router)
router.include_router(search.router)
router.include_router(geojson.router)
router.include_router(collections.router)
router.include_router(favorites.router)
