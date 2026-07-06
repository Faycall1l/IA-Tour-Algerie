import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_transit_routing
from app.models.wilaya_distance import WilayaDistance
from app.services.transit_routing import TransitRoutingService
from app.services.transport import TransportService

router = APIRouter(prefix="/transport", tags=["transport"])

_transport_service = TransportService()


# ── Legacy inter-wilaya route endpoints ─────────────────────────────

@router.get("/routes/{origin_wilaya_id}/{dest_wilaya_id}")
async def get_transport_route(
    origin_wilaya_id: int,
    dest_wilaya_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    route = await _transport_service.get_route(db, origin_wilaya_id, dest_wilaya_id)
    if route is None:
        return {"error": "No route found"}
    result = {
        "origin_wilaya_id": origin_wilaya_id,
        "dest_wilaya_id": dest_wilaya_id,
        "driving_distance_km": route.driving_distance_km,
        "driving_time_minutes": route.driving_time_minutes,
        "travel_time_label": route.travel_time_label(),
        "road_classification": route.road_classification,
        "has_train_route": route.has_train_route,
        "has_direct_flight": route.has_direct_flight,
        "estimated_costs_dzd": {
            "bus": route.estimate_bus_cost(),
            "shared_taxi": route.estimate_shared_taxi_cost(),
            "shared_taxi_per_person": route.estimate_shared_taxi_cost_per_person(),
            "private_taxi": route.estimate_private_taxi_cost(),
        },
    }
    train = route.estimate_train_cost()
    if train is not None:
        result["estimated_costs_dzd"]["train"] = train
    plane = route.estimate_plane_cost()
    if plane is not None:
        result["estimated_costs_dzd"]["plane"] = plane
    ferry = route.estimate_ferry_cost()
    if ferry is not None:
        result["estimated_costs_dzd"]["ferry"] = ferry
    return result


@router.get("/routes/from/{origin_wilaya_id}")
async def get_routes_from(
    origin_wilaya_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
) -> dict:
    stmt = (
        select(WilayaDistance)
        .where(
            or_(
                WilayaDistance.origin_wilaya_id == origin_wilaya_id,
                WilayaDistance.dest_wilaya_id == origin_wilaya_id,
            )
        )
        .order_by(WilayaDistance.driving_distance_km)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    destinations = []
    for r in rows:
        same_origin = r.origin_wilaya_id == origin_wilaya_id
        other_id = r.dest_wilaya_id if same_origin else r.origin_wilaya_id
        destinations.append(
            {
                "dest_wilaya_id": other_id,
                "driving_distance_km": r.driving_distance_km,
                "driving_time_minutes": r.driving_time_minutes,
            }
        )
    return {"origin_wilaya_id": origin_wilaya_id, "destinations": destinations}


# ── New multi-modal transit routing endpoints ──────────────────────

@router.get("/stations")
async def list_stations(
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
    wilaya_id: int | None = Query(None),
    station_type: str | None = Query(None, alias="type"),
) -> list:
    return await routing.list_stations(db, wilaya_id, station_type)


@router.get("/stations/nearby")
async def nearest_stations(
    lat: float = Query(...),
    lng: float = Query(...),
    limit: int = Query(5, le=20),
    station_type: str | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
) -> list:
    types = [station_type] if station_type else None
    return await routing.nearest_stations(db, lat, lng, limit, types)


@router.get("/lines")
async def list_lines(
    mode: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
) -> list:
    return await routing.list_lines(db, mode)


@router.get("/plan")
async def plan_route(
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    to_lat: float = Query(...),
    to_lng: float = Query(...),
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
) -> dict:
    """Plan a multi-modal public transit route between two GPS coordinates."""
    result = await routing.find_route(db, from_lat, from_lng, to_lat, to_lng)
    if result is None:
        return {"error": "No route found between these locations"}
    return result.model_dump(mode="json")


@router.get("/access/{poi_id}")
async def poi_access(
    poi_id: uuid.UUID,
    lat: float = Query(...),
    lng: float = Query(...),
    name: str = Query(""),
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
) -> dict:
    """Get public transit access info for a POI: nearest stations + routing."""
    result = await routing.poi_access(db, poi_id, lat, lng, name)
    return result.model_dump(mode="json")
