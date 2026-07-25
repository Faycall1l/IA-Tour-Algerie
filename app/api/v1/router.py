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
    health,
    pois,
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
router.include_router(artisans.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(discover.router)
router.include_router(events.router)
router.include_router(pois.router)
router.include_router(users.router)
router.include_router(wilayas.router)
router.include_router(experiences.router)
router.include_router(stays.router)
router.include_router(transport.router)
router.include_router(trips.router)
router.include_router(search.router)
router.include_router(geojson.router)
router.include_router(collections.router)
router.include_router(favorites.router)
