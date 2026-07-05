from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.transport import TransportService

router = APIRouter(prefix="/transport", tags=["transport"])

_transport_service = TransportService()


@router.get("/routes/{origin_wilaya_id}/{dest_wilaya_id}")
async def get_transport_route(
    origin_wilaya_id: int,
    dest_wilaya_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get real road distance, driving time, and transport cost estimates between two wilayas."""
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
            "private_taxi": route.estimate_private_taxi_cost(),
        },
    }
    train = route.estimate_train_cost()
    if train is not None:
        result["estimated_costs_dzd"]["train"] = train
    plane = route.estimate_plane_cost()
    if plane is not None:
        result["estimated_costs_dzd"]["plane"] = plane
    return result


@router.get("/routes/from/{origin_wilaya_id}")
async def get_routes_from(
    origin_wilaya_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
) -> dict:
    """Get top reachable wilayas from a given wilaya, sorted by driving distance."""
    from sqlalchemy import or_, select

    from app.models.wilaya_distance import WilayaDistance

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
