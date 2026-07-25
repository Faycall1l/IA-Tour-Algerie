from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    agents,
    artisans,
    auth,
    collections,
    discover,
    events,
    experiences,
    favorites,
    geojson,
    preferences,
    recommendations,
    health,
    pois,
    price_calendar,
    prices,
    reviews,
    search,
    stays,
    stats,
    suggestions,
    transport,
    trips,
    users,
    visits,
    wilayas,
)

router = APIRouter(prefix="/api/v1")
router.include_router(admin.router)
router.include_router(agents.router)
router.include_router(artisans.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(discover.router)
router.include_router(events.router)
router.include_router(pois.router)
router.include_router(price_calendar.router)
router.include_router(prices.router)
router.include_router(reviews.router)
router.include_router(users.router)
router.include_router(wilayas.router)
router.include_router(experiences.router)
router.include_router(stats.router)
router.include_router(stays.router)
router.include_router(transport.router)
router.include_router(suggestions.router)
router.include_router(trips.router)
router.include_router(search.router)
router.include_router(geojson.router)
router.include_router(collections.router)
router.include_router(favorites.router)
router.include_router(preferences.router)
router.include_router(recommendations.router)
router.include_router(visits.router)
