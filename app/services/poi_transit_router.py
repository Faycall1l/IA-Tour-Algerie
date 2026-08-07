"""
Multi-modal POI transit router with turn-by-turn directions.

Combines walking + public transit to compute optimal routes from a user's
GPS location to any POI or destination. Returns structured, step-by-step
directions with milestones for mode changes.

Uses the existing TransitGraph for intra-city transit routing and
haversine-based walking estimates for first/last-mile segments.
"""

import math
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.poi import POI
from app.models.station import LineStop, Station, TransportLine
from app.schemas.transport import (
    NearestStation,
    StationLineRef,
    StationRead,
)
from app.services.transit_routing import (
    TransitGraph,
    TransitRoutingService,
    _haversine_km,
)

WALK_SPEED_KMH = 4.5
MAX_WALK_KM = 2.0
MAX_NEARBY_STATIONS = 5


@dataclass
class StepCoordinate:
    lat: float
    lng: float
    name: str


@dataclass
class WalkingStep:
    """Walking from one point to another (first/last mile or transfer)."""

    from_location: StepCoordinate
    to_location: StepCoordinate
    distance_km: float
    estimated_minutes: int
    description: str


@dataclass
class TransitStep:
    """Riding a transit line between two stations."""

    mode: str
    line_name: str
    line_color: str | None
    operator: str
    from_station: StationRead
    to_station: StationRead
    stop_count: int
    distance_km: float
    estimated_minutes: int
    schedule: dict | None
    pricing: dict | None


@dataclass
class TransferStep:
    """Changing lines at an intermediate station."""

    station: StationRead
    from_line: str
    to_line: str
    wait_minutes: int
    description: str


@dataclass
class RoutePlan:
    """A complete point-to-point route with walking + transit segments."""

    from_lat: float
    from_lng: float
    from_name: str
    to_lat: float
    to_lng: float
    to_name: str
    total_walking_km: float
    total_transit_km: float
    total_transfers: int
    total_estimated_minutes: int
    steps: list[WalkingStep | TransitStep | TransferStep] = field(default_factory=list)
    available_modes: list[str] = field(default_factory=list)
    is_walking_only: bool = False
    is_driving_recommended: bool = False

    def as_dict(self) -> dict:
        result: dict = {
            "from": {"lat": self.from_lat, "lng": self.from_lng, "name": self.from_name},
            "to": {"lat": self.to_lat, "lng": self.to_lng, "name": self.to_name},
            "total_walking_km": round(self.total_walking_km, 2),
            "total_transit_km": round(self.total_transit_km, 2),
            "total_transfers": self.total_transfers,
            "total_estimated_minutes": self.total_estimated_minutes,
            "available_modes": self.available_modes,
            "is_walking_only": self.is_walking_only,
            "is_driving_recommended": self.is_driving_recommended,
            "steps": [],
        }
        for step in self.steps:
            if isinstance(step, WalkingStep):
                result["steps"].append(
                    {
                        "type": "walking",
                        "description": step.description,
                        "from": {
                            "lat": step.from_location.lat,
                            "lng": step.from_location.lng,
                            "name": step.from_location.name,
                        },
                        "to": {
                            "lat": step.to_location.lat,
                            "lng": step.to_location.lng,
                            "name": step.to_location.name,
                        },
                        "distance_km": round(step.distance_km, 2),
                        "estimated_minutes": step.estimated_minutes,
                    }
                )
            elif isinstance(step, TransitStep):
                result["steps"].append(
                    {
                        "type": "transit",
                        "mode": step.mode,
                        "line_name": step.line_name,
                        "line_color": step.line_color,
                        "operator": step.operator,
                        "from_station": step.from_station.model_dump(mode="json"),
                        "to_station": step.to_station.model_dump(mode="json"),
                        "stop_count": step.stop_count,
                        "distance_km": round(step.distance_km, 2),
                        "estimated_minutes": step.estimated_minutes,
                        "schedule": step.schedule,
                        "pricing": step.pricing,
                    }
                )
            elif isinstance(step, TransferStep):
                result["steps"].append(
                    {
                        "type": "transfer",
                        "description": step.description,
                        "station": step.station.model_dump(mode="json"),
                        "from_line": step.from_line,
                        "to_line": step.to_line,
                        "wait_minutes": step.wait_minutes,
                    }
                )
        return result


class PoiTransitRouter:
    """Routes from GPS coordinates to POIs using walking + public transit.

    Combines:
      - Walking from origin to nearest transit station
      - Public transit via the in-memory TransitGraph (Dijkstra)
      - Walking from last station to destination POI

    Handles edge cases:
      - No transit nearby → walking-only or driving-recommended
      - POI within walking distance → direct walk
      - Multi-leg routes with transfers
    """

    def __init__(self, transit_routing: TransitRoutingService) -> None:
        self._routing = transit_routing
        self._graph: TransitGraph | None = None
        self._line_cache: dict[uuid.UUID, TransportLine] = {}

    async def _ensure_loaded(self, db: AsyncSession) -> TransitGraph:
        await self._routing.ensure_loaded(db)
        if self._graph is None:
            self._graph = self._routing._graph
            lines = (await db.execute(select(TransportLine))).scalars().all()
            self._line_cache = {line.id: line for line in lines}
        return self._graph

    def _walk_time(self, km: float) -> int:
        return max(1, int(km / WALK_SPEED_KMH * 60))

    def _station_nearby(self, lat: float, lng: float, station: Station) -> float:
        return _haversine_km(lat, lng, station.latitude, station.longitude)

    def _station_to_read(
        self, s: Station, lines: dict[uuid.UUID, list[StationLineRef]]
    ) -> StationRead:
        return StationRead(
            id=s.id,
            name=s.name,
            name_ar=s.name_ar,
            name_en=s.name_en,
            wilaya_id=s.wilaya_id,
            latitude=s.latitude,
            longitude=s.longitude,
            station_type=s.station_type,
            operator=s.operator,
            address=s.address,
            is_active=s.is_active,
        )

    async def _build_station_lines(self, db: AsyncSession) -> dict[uuid.UUID, list[StationLineRef]]:
        rows = await db.execute(
            select(LineStop).join(TransportLine, LineStop.line_id == TransportLine.id)
        )
        stops = rows.scalars().all()
        station_lines: dict[uuid.UUID, list[StationLineRef]] = {}
        for stop in stops:
            sid = stop.station_id
            if sid not in station_lines:
                station_lines[sid] = []
            station_lines[sid].append(
                StationLineRef(
                    line_id=stop.line.id,
                    line_name=stop.line.name,
                    mode=stop.line.mode,
                    operator=stop.line.operator,
                    color=stop.line.color,
                    stop_order=stop.stop_order,
                )
            )
        return station_lines

    async def route_to_poi(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
        from_lat: float,
        from_lng: float,
        from_name: str = "Your location",
    ) -> RoutePlan:
        """Compute turn-by-turn directions from user location to a POI."""
        poi = await db.get(POI, poi_id)
        if poi is None:
            raise ValueError(f"POI {poi_id} not found")

        return await self.route_to(
            db=db,
            from_lat=from_lat,
            from_lng=from_lng,
            from_name=from_name,
            to_lat=poi.latitude,
            to_lng=poi.longitude,
            to_name=poi.name,
        )

    async def route_to(
        self,
        db: AsyncSession,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
        from_name: str = "Your location",
        to_name: str = "Destination",
    ) -> RoutePlan:
        """Compute turn-by-turn directions between two GPS points."""
        graph = await self._ensure_loaded(db)
        station_lines = await self._build_station_lines(db)

        direct_walk_km = _haversine_km(from_lat, from_lng, to_lat, to_lng)

        from_nearby = graph.nearest_stations(from_lat, from_lng, limit=MAX_NEARBY_STATIONS)
        to_nearby = graph.nearest_stations(to_lat, to_lng, limit=MAX_NEARBY_STATIONS)

        from_nearby = [(s, d) for s, d in from_nearby if d <= MAX_WALK_KM]
        to_nearby = [(s, d) for s, d in to_nearby if d <= MAX_WALK_KM]

        if not from_nearby and not to_nearby:
            return RoutePlan(
                from_lat=from_lat,
                from_lng=from_lng,
                from_name=from_name,
                to_lat=to_lat,
                to_lng=to_lng,
                to_name=to_name,
                total_walking_km=direct_walk_km,
                total_transit_km=0,
                total_transfers=0,
                total_estimated_minutes=self._walk_time(direct_walk_km),
                steps=[
                    WalkingStep(
                        from_location=StepCoordinate(from_lat, from_lng, from_name),
                        to_location=StepCoordinate(to_lat, to_lng, to_name),
                        distance_km=direct_walk_km,
                        estimated_minutes=self._walk_time(direct_walk_km),
                        description=(
                            f"Walk {direct_walk_km:.1f} km "
                            f"({self._walk_time(direct_walk_km)} min) to {to_name}. "
                            f"No transit stations within {MAX_WALK_KM} km."
                        ),
                    )
                ],
                available_modes=["walking"],
                is_walking_only=True,
                is_driving_recommended=direct_walk_km > 1.0,
            )

        if not from_nearby:
            nearest_to = to_nearby[0] if to_nearby else (None, 0)
            return RoutePlan(
                from_lat=from_lat,
                from_lng=from_lng,
                from_name=from_name,
                to_lat=to_lat,
                to_lng=to_lng,
                to_name=to_name,
                total_walking_km=direct_walk_km,
                total_transit_km=0,
                total_transfers=0,
                total_estimated_minutes=self._walk_time(direct_walk_km),
                steps=[
                    WalkingStep(
                        from_location=StepCoordinate(from_lat, from_lng, from_name),
                        to_location=StepCoordinate(to_lat, to_lng, to_name),
                        distance_km=direct_walk_km,
                        estimated_minutes=self._walk_time(direct_walk_km),
                        description=(
                            f"No station near origin. Walk {direct_walk_km:.1f} km "
                            f"({self._walk_time(direct_walk_km)} min) or drive. "
                            f"Nearest station: {nearest_to[0].name if nearest_to[0] else 'none'}"
                        ),
                    )
                ],
                available_modes=["walking", "driving"],
                is_driving_recommended=True,
            )

        if not to_nearby:
            return RoutePlan(
                from_lat=from_lat,
                from_lng=from_lng,
                from_name=from_name,
                to_lat=to_lat,
                to_lng=to_lng,
                to_name=to_name,
                total_walking_km=direct_walk_km,
                total_transit_km=0,
                total_transfers=0,
                total_estimated_minutes=self._walk_time(direct_walk_km),
                steps=[
                    WalkingStep(
                        from_location=StepCoordinate(from_lat, from_lng, from_name),
                        to_location=StepCoordinate(to_lat, to_lng, to_name),
                        distance_km=direct_walk_km,
                        estimated_minutes=self._walk_time(direct_walk_km),
                        description=(
                            f"No station near {to_name}. Walk {direct_walk_km:.1f} km "
                            f"({self._walk_time(direct_walk_km)} min) or drive."
                        ),
                    )
                ],
                available_modes=["walking", "driving"],
                is_driving_recommended=True,
            )

        best_plan: RoutePlan | None = None
        best_cost = float("inf")
        seen_modes: set[str] = set()

        for from_s, from_walk in from_nearby:
            for to_s, to_walk in to_nearby:
                route = graph.find_route(from_s.id, to_s.id)

                if route is None:
                    continue

                from_walk_min = self._walk_time(from_walk)
                to_walk_min = self._walk_time(to_walk)
                transit_min = route.total_estimated_minutes or 0
                transit_km = sum(
                    _haversine_km(
                        graph._stations[seg.from_station_id].latitude,
                        graph._stations[seg.from_station_id].longitude,
                        graph._stations[seg.to_station_id].latitude,
                        graph._stations[seg.to_station_id].longitude,
                    )
                    for seg in route.segments
                    if seg.operator != "Transfer"
                )

                total_min = from_walk_min + transit_min + to_walk_min

                if total_min < best_cost:
                    best_cost = total_min

                    steps: list[WalkingStep | TransitStep | TransferStep] = []

                    from_station_read = self._station_to_read(from_s, station_lines)

                    steps.append(
                        WalkingStep(
                            from_location=StepCoordinate(from_lat, from_lng, from_name),
                            to_location=StepCoordinate(
                                from_s.latitude, from_s.longitude, from_s.name
                            ),
                            distance_km=from_walk,
                            estimated_minutes=from_walk_min,
                            description=(
                                f"Walk {from_walk_min} min ({from_walk:.1f} km) to {from_s.name}"
                            ),
                        )
                    )

                    for seg in route.segments:
                        if seg.operator == "Transfer":
                            if seg.from_station_id in graph._stations:
                                st = graph._stations[seg.from_station_id]
                                st_read = self._station_to_read(st, station_lines)
                                steps.append(
                                    TransferStep(
                                        station=st_read,
                                        from_line="",
                                        to_line=seg.line_name,
                                        wait_minutes=5,
                                        description=f"Transfer at {st.name} — {seg.line_name}",
                                    )
                                )
                        else:
                            from_st = graph._stations.get(seg.from_station_id)
                            to_st = graph._stations.get(seg.to_station_id)
                            if from_st and to_st:
                                seg_dist = _haversine_km(
                                    from_st.latitude,
                                    from_st.longitude,
                                    to_st.latitude,
                                    to_st.longitude,
                                )
                                from_read = (
                                    self._station_to_read(from_st, station_lines)
                                    if from_st
                                    else from_station_read
                                )
                                to_read = self._station_to_read(to_st, station_lines)
                                line = self._line_cache.get(seg.line_id)
                                schedule = line.schedule_info if line else None
                                pricing = line.pricing_info if line else None
                                seen_modes.add(seg.mode)
                                steps.append(
                                    TransitStep(
                                        mode=seg.mode,
                                        line_name=seg.line_name,
                                        line_color=seg.line_color,
                                        operator=seg.operator,
                                        from_station=from_read,
                                        to_station=to_read,
                                        stop_count=seg.stop_count,
                                        distance_km=seg_dist,
                                        estimated_minutes=seg.estimated_minutes or 0,
                                        schedule=schedule,
                                        pricing=pricing,
                                    )
                                )

                    steps.append(
                        WalkingStep(
                            from_location=StepCoordinate(to_s.latitude, to_s.longitude, to_s.name),
                            to_location=StepCoordinate(to_lat, to_lng, to_name),
                            distance_km=to_walk,
                            estimated_minutes=to_walk_min,
                            description=(
                                f"Walk {to_walk_min} min ({to_walk:.1f} km) "
                                f"from {to_s.name} to {to_name}"
                            ),
                        )
                    )

                    transfers = sum(1 for s in route.segments if s.operator == "Transfer")

                    best_plan = RoutePlan(
                        from_lat=from_lat,
                        from_lng=from_lng,
                        from_name=from_name,
                        to_lat=to_lat,
                        to_lng=to_lng,
                        to_name=to_name,
                        total_walking_km=from_walk + to_walk,
                        total_transit_km=transit_km,
                        total_transfers=transfers,
                        total_estimated_minutes=total_min,
                        steps=steps,
                        available_modes=sorted(seen_modes),
                    )

        if best_plan is None:
            return RoutePlan(
                from_lat=from_lat,
                from_lng=from_lng,
                from_name=from_name,
                to_lat=to_lat,
                to_lng=to_lng,
                to_name=to_name,
                total_walking_km=direct_walk_km,
                total_transit_km=0,
                total_transfers=0,
                total_estimated_minutes=self._walk_time(direct_walk_km),
                steps=[
                    WalkingStep(
                        from_location=StepCoordinate(from_lat, from_lng, from_name),
                        to_location=StepCoordinate(to_lat, to_lng, to_name),
                        distance_km=direct_walk_km,
                        estimated_minutes=self._walk_time(direct_walk_km),
                        description=(
                            f"No transit route found. Walk {direct_walk_km:.1f} km "
                            f"({self._walk_time(direct_walk_km)} min) or drive."
                        ),
                    )
                ],
                available_modes=["walking", "driving"],
                is_driving_recommended=direct_walk_km > 1.0,
            )

        best_plan.available_modes = sorted(seen_modes | {"walking"})
        if best_plan.total_transit_km == 0 and direct_walk_km > 1.0:
            best_plan.is_driving_recommended = True
            if "driving" not in best_plan.available_modes:
                best_plan.available_modes.append("driving")
        return best_plan

    async def poi_access(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
        poi_lat: float,
        poi_lng: float,
        poi_name: str,
    ) -> dict:
        """Get transit access info including route alternatives."""
        graph = await self._ensure_loaded(db)
        station_lines = await self._build_station_lines(db)

        nearest = graph.nearest_stations(poi_lat, poi_lng, limit=MAX_NEARBY_STATIONS)
        nearby_stations: list[dict] = []
        for s, dist in nearest:
            nearby_stations.append(
                {
                    "station": self._station_to_read(s, station_lines).model_dump(mode="json"),
                    "distance_km": round(dist, 2),
                    "walking_minutes": self._walk_time(dist),
                    "lines": [sl.model_dump(mode="json") for sl in station_lines.get(s.id, [])],
                }
            )

        modes_at_stations: set[str] = set()
        for s, _ in nearest:
            for sl in station_lines.get(s.id, []):
                modes_at_stations.add(sl.mode)

        return {
            "poi_id": str(poi_id),
            "poi_name": poi_name,
            "poi_lat": poi_lat,
            "poi_lng": poi_lng,
            "nearby_stations": nearby_stations,
            "available_transit_modes": sorted(modes_at_stations),
            "has_transit_access": len(nearest) > 0 and any(d <= MAX_WALK_KM for _, d in nearest),
            "closest_station": (nearby_stations[0] if nearby_stations else None),
        }
