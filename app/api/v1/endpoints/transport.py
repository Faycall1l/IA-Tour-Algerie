import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_poi_transit_router, get_transit_routing
from app.models.wilaya_distance import WilayaDistance
from app.services.multimodal_router import MultiModalRouter
from app.services.poi_transit_router import PoiTransitRouter
from app.services.transit_routing import TransitRoutingService
from app.services.transport import TransportService

router = APIRouter(prefix="/transport", tags=["transport"])

_transport_service = TransportService()


# ── Legacy inter-wilaya route endpoints ─────────────────────────────


@router.get(
    "/routes/from/{origin_wilaya_id}",
    summary="Destinations from a wilaya",
    description="List reachable wilayas from an origin with driving distance/time, ordered by distance.",  # noqa: E501
    responses={
        422: {"description": "Invalid origin_wilaya_id"},
        200: {"description": "Origin + destinations with driving estimates"},
    },
)
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


@router.get(
    "/routes/{origin_wilaya_id}/{dest_wilaya_id}",
    summary="Inter-wilaya transport options",
    description=(
        "Multi-modal options (train, bus, taxi, flight) between two wilayas with schedules, "
        "pricing, transfers, and operator contacts. Falls back to driving estimates when no "
        "scheduled line exists."
    ),
    responses={
        200: {"description": "Options list + driving estimates"},
        422: {"description": "Invalid wilaya ids"},
    },
)
async def get_transport_route(
    origin_wilaya_id: int,
    dest_wilaya_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get multi-modal transport options between two wilayas.

    Returns driving estimates plus real train, bus, and flight options
    with schedules, pricing, and operator contacts when available.
    """
    # Multi-modal options
    router_instance = MultiModalRouter()
    options = await router_instance.get_inter_wilaya_options(db, origin_wilaya_id, dest_wilaya_id)

    if not options:
        # Fallback to legacy flat estimates
        route = await _transport_service.get_route(db, origin_wilaya_id, dest_wilaya_id)
        if route is None:
            return {"error": "No route found"}
        return {
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
            "options": [],
        }

    result_options = []
    driving_dist = None
    driving_time = None
    for opt in options:
        opt_dict = {
            "mode": opt.mode,
            "line_name": opt.line_name,
            "operator": opt.operator,
            "cost_dzd": opt.cost_dzd,
            "duration_min": opt.duration_min,
            "schedule": opt.schedule,
            "pricing": opt.pricing,
            "transfers": opt.transfers,
            "contacts": [
                {
                    "name": c.name,
                    "mode": c.mode,
                    "phone": c.phone,
                    "website": c.website,
                    "email": c.email,
                }
                for c in opt.contacts
            ],
        }
        result_options.append(opt_dict)
        if opt.mode == "driving":
            driving_time = opt.duration_min
            if opt.pricing:
                driving_dist = opt.pricing.get("private_taxi", 0) / 20.0

    return {
        "origin_wilaya_id": origin_wilaya_id,
        "dest_wilaya_id": dest_wilaya_id,
        "driving_distance_km": driving_dist,
        "driving_time_minutes": driving_time,
        "options": result_options,
    }


# ── New multi-modal transit routing endpoints ──────────────────────


@router.get(
    "/stations",
    summary="List stations",
    description="All transit stations, optionally filtered by wilaya and type (bus, train, tram, taxi, airport, ferry, cablecar).",  # noqa: E501
    responses={
        200: {"description": "Station list"},
        422: {"description": "Invalid filter"},
    },
)
async def list_stations(
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
    wilaya_id: int | None = Query(None),
    station_type: str | None = Query(None, alias="type"),
) -> list:
    return await routing.list_stations(db, wilaya_id, station_type)


@router.get(
    "/stations/nearby",
    summary="Nearest stations",
    description="Stations nearest to a lat/lng point, optionally filtered by type. Uses the transit graph spatial index.",  # noqa: E501
    responses={
        200: {"description": "Stations with distance"},
        422: {"description": "Missing/invalid lat/lng"},
    },
)
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


@router.get(
    "/lines",
    summary="List transport lines",
    description="Transport lines, optionally filtered by mode (bus, train, tram, taxi, flight, ferry, cablecar, walking). Includes schedules and pricing.",  # noqa: E501
    responses={
        200: {"description": "Line list"},
        422: {"description": "Invalid mode"},
    },
)
async def list_lines(
    mode: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    routing: TransitRoutingService = Depends(get_transit_routing),
) -> list:
    return await routing.list_lines(db, mode)


@router.get(
    "/plan",
    summary="Plan a transit route",
    description=(
        "Multi-modal route from a GPS point to a destination with turn-by-turn steps: walking, "
        "transit (schedule + pricing), and transfers as milestones for line changes. Handles "
        "walking-only and driving-recommended cases."
    ),
    responses={
        200: {"description": "RoutePlan with steps, duration, cost"},
        422: {"description": "Missing/invalid coordinates"},
    },
)
async def plan_route(
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    to_lat: float = Query(...),
    to_lng: float = Query(...),
    from_name: str = Query("Your location"),
    to_name: str = Query("Destination"),
    db: AsyncSession = Depends(get_db),
    router: PoiTransitRouter = Depends(get_poi_transit_router),
) -> dict:
    """Plan a multi-modal transit route with walking + transit turn-by-turn directions."""
    plan = await router.route_to(
        db=db,
        from_lat=from_lat,
        from_lng=from_lng,
        from_name=from_name,
        to_lat=to_lat,
        to_lng=to_lng,
        to_name=to_name,
    )
    return plan.as_dict()


@router.get(
    "/access/{poi_id}",
    summary="Transit access for a POI",
    description="Nearest stations and routing summary for a POI, useful for the 'how to get there' panel.",  # noqa: E501
    responses={
        200: {"description": "Nearest stations + distances"},
        404: {"description": "POI not found"},
        422: {"description": "Invalid UUID"},
    },
)
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


@router.get(
    "/route-to-poi/{poi_id}",
    summary="Directions to a POI",
    description=(
        "Turn-by-turn transit directions from a GPS point to a specific POI. Returns the plan "
        "plus POI access info. Falls back to an error object when no route exists."
    ),
    responses={
        200: {"description": "Route plan + POI access info"},
        404: {"description": "POI not found"},
        422: {"description": "Invalid UUID or coordinates"},
    },
)
async def route_to_poi(
    poi_id: uuid.UUID,
    from_lat: float = Query(...),
    from_lng: float = Query(...),
    from_name: str = Query("Your location"),
    db: AsyncSession = Depends(get_db),
    router: PoiTransitRouter = Depends(get_poi_transit_router),
) -> dict:
    """Compute turn-by-turn transit directions from a GPS point to a specific POI.

    Returns walking + transit segments with milestones for mode changes.
    Handles: walking-only routes, multi-leg transit, no-transit-available fallbacks.
    """
    try:
        plan = await router.route_to_poi(
            db=db,
            poi_id=poi_id,
            from_lat=from_lat,
            from_lng=from_lng,
            from_name=from_name,
        )
        access_info = await router.poi_access(
            db=db,
            poi_id=poi_id,
            poi_lat=plan.to_lat,
            poi_lng=plan.to_lng,
            poi_name=plan.to_name,
        )
        return {
            "poi_id": str(poi_id),
            "poi_name": plan.to_name,
            "poi_lat": plan.to_lat,
            "poi_lng": plan.to_lng,
            "from": {"lat": plan.from_lat, "lng": plan.from_lng, "name": plan.from_name},
            "plan": plan.as_dict(),
            "poi_access": access_info,
        }
    except ValueError as e:
        return {"error": str(e)}


# ── Transport operators ──────────────────────────────────────────────


@router.get(
    "/operators",
    summary="List transport operators",
    description="Active transport operators with contact info (phone, website, email) and coverage, filtered by mode: train, flight, bus, taxi, tram, cablecar, ferry.",  # noqa: E501
    responses={
        200: {"description": "Operator list with contacts"},
        422: {"description": "Invalid mode"},
    },
)
async def list_operators(
    db: AsyncSession = Depends(get_db),
    mode: str | None = Query(
        None, description="Filter by mode: train, flight, bus, taxi, tram, cablecar"
    ),
) -> list:
    """List transport operators with contact information."""
    from sqlalchemy import text as sa_text

    conditions = ["is_active = TRUE"]
    bind: dict = {}
    if mode:
        conditions.append("mode = :mode")
        bind["mode"] = mode
    where = " AND ".join(conditions)
    rows = await db.execute(
        sa_text(
            f"SELECT name, name_ar, mode, phone, website, email, "
            f"headquarters_wilaya_id, description, coverage_type "
            f"FROM transport_operators WHERE {where} ORDER BY mode, name"
        ),
        bind,
    )
    return [
        {
            "name": r[0],
            "name_ar": r[1],
            "mode": r[2],
            "phone": r[3],
            "website": r[4],
            "email": r[5],
            "headquarters_wilaya_id": r[6],
            "description": r[7],
            "coverage_type": r[8],
        }
        for r in rows.all()
    ]
