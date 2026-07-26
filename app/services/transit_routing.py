"""
Multi-modal transit routing service for Algeria.

Builds a graph from stations + line_stops in the database and finds
shortest paths using BFS / Dijkstra across all modes (train, metro, tram, bus).
"""
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.station import LineStop, Station, TransportLine
from app.schemas.transport import (
    NearestStation,
    POIAccess,
    RouteResult,
    RouteSegment,
    StationLineRef,
    StationRead,
)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class GraphEdge:
    to_station_id: uuid.UUID
    line_id: uuid.UUID
    line_name: str
    mode: str
    operator: str
    color: str | None
    weight: float  # km between stations


@dataclass
class _Node:
    station_id: uuid.UUID
    dist: float
    transfers: int
    prev: uuid.UUID | None = None
    edge: GraphEdge | None = None


class TransitGraph:
    """In-memory graph of all transit stations and connections."""

    def __init__(self) -> None:
        self._adj: dict[uuid.UUID, list[GraphEdge]] = defaultdict(list)
        self._stations: dict[uuid.UUID, Station] = {}
        self._station_name_map: dict[str, uuid.UUID] = {}

    async def load(self, db: AsyncSession) -> None:
        stations = (await db.execute(select(Station))).scalars().all()
        lines = (await db.execute(select(TransportLine))).scalars().all()
        stops = (await db.execute(select(LineStop))).scalars().all()

        for s in stations:
            self._stations[s.id] = s
            self._station_name_map[s.name] = s.id

        stops_by_line: dict[uuid.UUID, list[LineStop]] = defaultdict(list)
        for stop in stops:
            stops_by_line[stop.line_id].append(stop)

        line_map = {l.id: l for l in lines}

        for line_id, line_stops in stops_by_line.items():
            line = line_map.get(line_id)
            if not line:
                continue
            line_stops.sort(key=lambda x: x.stop_order)
            for i in range(len(line_stops) - 1):
                a = line_stops[i]
                b = line_stops[i + 1]
                dist = _haversine_km(
                    self._stations[a.station_id].latitude,
                    self._stations[a.station_id].longitude,
                    self._stations[b.station_id].latitude,
                    self._stations[b.station_id].longitude,
                )
                edge = GraphEdge(
                    to_station_id=b.station_id,
                    line_id=line_id,
                    line_name=line.name,
                    mode=line.mode,
                    operator=line.operator,
                    color=line.color,
                    weight=max(dist, 0.5),
                )
                self._adj[a.station_id].append(edge)
                rev = GraphEdge(
                    to_station_id=a.station_id,
                    line_id=line_id,
                    line_name=line.name,
                    mode=line.mode,
                    operator=line.operator,
                    color=line.color,
                    weight=max(dist, 0.5),
                )
                self._adj[b.station_id].append(rev)

        self._add_transfers(stops_by_line, line_map)

    def _add_transfers(self, stops_by_line: dict[uuid.UUID, list[LineStop]],
                       line_map: dict[uuid.UUID, TransportLine]) -> None:
        station_lines: dict[uuid.UUID, list[tuple[uuid.UUID, str, str, str | None]]] = defaultdict(list)
        for line_id, line_stops in stops_by_line.items():
            line = line_map.get(line_id)
            if not line:
                continue
            for stop in line_stops:
                station_lines[stop.station_id].append((line_id, line.name, line.mode, line.color))

        for station_id, lines_at_station in station_lines.items():
            if len(lines_at_station) < 2:
                continue
            for i in range(len(lines_at_station)):
                for j in range(i + 1, len(lines_at_station)):
                    li = lines_at_station[i]
                    lj = lines_at_station[j]
                    self._adj[station_id].append(GraphEdge(
                        to_station_id=station_id,
                        line_id=li[0],
                        line_name=f"Transfer: {li[1]} ↔ {lj[1]}",
                        mode=lj[2],
                        operator="Transfer",
                        color=lj[3],
                        weight=0.0,
                    ))
                    self._adj[station_id].append(GraphEdge(
                        to_station_id=station_id,
                        line_id=lj[0],
                        line_name=f"Transfer: {lj[1]} ↔ {li[1]}",
                        mode=li[2],
                        operator="Transfer",
                        color=li[3],
                        weight=0.0,
                    ))

    def get_station_by_name(self, name: str) -> Station | None:
        sid = self._station_name_map.get(name)
        if sid:
            return self._stations.get(sid)
        return None

    @property
    def all_stations(self) -> list[Station]:
        return list(self._stations.values())

    def find_route(self, from_station_id: uuid.UUID, to_station_id: uuid.UUID) -> RouteResult | None:
        if from_station_id == to_station_id:
            return None

        from_station = self._stations.get(from_station_id)
        to_station = self._stations.get(to_station_id)
        if not from_station or not to_station:
            return None

        best: dict[uuid.UUID, _Node] = {}
        pq: list[tuple[float, int, uuid.UUID]] = [(0, 0, from_station_id)]
        best[from_station_id] = _Node(from_station_id, 0, 0)

        while pq:
            dist, transfers, sid = heappop(pq)
            node = best.get(sid)
            if node is None or node.dist < dist:
                continue
            if sid == to_station_id:
                break
            for edge in self._adj.get(sid, []):
                nd = dist + edge.weight
                nt = transfers + (0 if edge.operator == "Transfer" else int(edge.weight > 0))
                existing = best.get(edge.to_station_id)
                if existing is None or nd < existing.dist:
                    best[edge.to_station_id] = _Node(edge.to_station_id, nd, nt, sid, edge)
                    heappush(pq, (nd, nt, edge.to_station_id))

        if to_station_id not in best:
            return None

        segments: list[RouteSegment] = []
        cur = to_station_id
        path: list[tuple[uuid.UUID, GraphEdge]] = []
        while cur != from_station_id:
            node = best.get(cur)
            if node is None or node.edge is None:
                break
            path.append((cur, node.edge))
            cur = node.prev  # type: ignore[assignment]
        path.reverse()

        total_min = 0
        i = 0
        while i < len(path):
            _sid, cur_edge = path[i]
            if cur_edge.operator == "Transfer":
                from_sid = from_station_id if i == 0 else path[i - 1][0]
                segments.append(RouteSegment(
                    mode=cur_edge.mode,
                    operator="Transfer",
                    line_name=cur_edge.line_name,
                    line_color=cur_edge.color,
                    from_station=self._stations[from_sid].name,
                    to_station=self._stations[from_sid].name,
                    from_station_id=from_sid,
                    to_station_id=from_sid,
                    stop_count=0,
                    estimated_minutes=0,
                    departure_time=None,
                    arrival_time=None,
                    pricing=None,
                    schedule=None,
                ))
                i += 1
                continue

            j = i + 1
            while j < len(path) and path[j][1].line_id == cur_edge.line_id and path[j][1].operator != "Transfer":
                j += 1

            from_sid = from_station_id if i == 0 else path[i - 1][0]
            to_sid = path[j - 1][0]

            stop_count = j - i + 1
            dist_km = sum(p[1].weight for p in path[i:j])
            est_min = max(1, int(dist_km / 30 * 60))
            total_min += est_min

            segments.append(RouteSegment(
                mode=cur_edge.mode,
                operator=cur_edge.operator,
                line_name=cur_edge.line_name,
                line_color=cur_edge.color,
                from_station=self._stations[from_sid].name,
                to_station=self._stations[to_sid].name,
                from_station_id=from_sid,
                to_station_id=to_sid,
                stop_count=stop_count,
                estimated_minutes=est_min,
                departure_time=None,
                arrival_time=None,
                pricing=None,
                schedule=None,
            ))
            i = j

        return RouteResult(
            from_lat=from_station.latitude,
            from_lng=from_station.longitude,
            to_lat=to_station.latitude,
            to_lng=to_station.longitude,
            from_name=from_station.name,
            to_name=to_station.name,
            segments=segments,
            total_transfers=sum(1 for s in segments if s.operator == "Transfer"),
            total_estimated_minutes=total_min,
        )

    def nearest_stations(self, lat: float, lng: float,
                         limit: int = 5, types: list[str] | None = None) -> list[tuple[Station, float]]:
        scored: list[tuple[float, Station]] = []
        for s in self._stations.values():
            if types and s.station_type not in types:
                continue
            d = _haversine_km(lat, lng, s.latitude, s.longitude)
            scored.append((d, s))
        scored.sort(key=lambda x: x[0])
        return [(s, d) for d, s in scored[:limit]]


class TransitRoutingService:
    """Service layer wrapping TransitGraph with DB loading."""

    def __init__(self) -> None:
        self._graph = TransitGraph()
        self._loaded = False

    async def ensure_loaded(self, db: AsyncSession) -> None:
        if not self._loaded:
            await self._graph.load(db)
            self._loaded = True

    async def find_route(self, db: AsyncSession,
                         from_lat: float, from_lng: float,
                         to_lat: float, to_lng: float) -> RouteResult | None:
        await self.ensure_loaded(db)
        from_stations = self._graph.nearest_stations(from_lat, from_lng, limit=3)
        to_stations = self._graph.nearest_stations(to_lat, to_lng, limit=3)
        best: RouteResult | None = None
        best_cost = float("inf")
        for fs, _ in from_stations:
            for ts, _ in to_stations:
                route = self._graph.find_route(fs.id, ts.id)
                if route and route.total_estimated_minutes and route.total_estimated_minutes < best_cost:
                    best = route
                    best_cost = route.total_estimated_minutes
        return best

    async def nearest_stations(self, db: AsyncSession, lat: float, lng: float,
                               limit: int = 5, types: list[str] | None = None) -> list[NearestStation]:
        await self.ensure_loaded(db)
        station_lines_map: dict[uuid.UUID, list[StationLineRef]] = {}
        rows = await db.execute(
            select(LineStop).join(TransportLine, LineStop.line_id == TransportLine.id)
        )
        stops = rows.scalars().all()
        for stop in stops:
            sid = stop.station_id
            if sid not in station_lines_map:
                station_lines_map[sid] = []
            station_lines_map[sid].append(StationLineRef(
                line_id=stop.line.id,
                line_name=stop.line.name,
                mode=stop.line.mode,
                operator=stop.line.operator,
                color=stop.line.color,
                stop_order=stop.stop_order,
            ))

        nearest = self._graph.nearest_stations(lat, lng, limit, types)
        result = []
        for s, dist in nearest:
            result.append(NearestStation(
                station=StationRead(
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
                ),
                distance_km=round(dist, 2),
                lines=station_lines_map.get(s.id, []),
            ))
        return result

    async def poi_access(self, db: AsyncSession, poi_id: uuid.UUID,
                         poi_lat: float, poi_lng: float,
                         poi_name: str) -> POIAccess:
        nearest = await self.nearest_stations(db, poi_lat, poi_lng, limit=3)
        return POIAccess(
            poi_id=poi_id,
            poi_name=poi_name,
            nearest_stations=nearest,
            route_to_poi=None,
        )

    async def list_stations(self, db: AsyncSession, wilaya_id: int | None = None,
                            station_type: str | None = None) -> list[StationRead]:
        await self.ensure_loaded(db)
        stations = self._graph.all_stations
        result = []
        for s in stations:
            if wilaya_id is not None and s.wilaya_id != wilaya_id:
                continue
            if station_type is not None and s.station_type != station_type:
                continue
            result.append(StationRead(
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
            ))
        return result

    async def list_lines(self, db: AsyncSession, mode: str | None = None) -> list:
        await self.ensure_loaded(db)
        rows = await db.execute(select(TransportLine))
        lines = rows.scalars().all()
        result = []
        for line in lines:
            if mode and line.mode != mode:
                continue
            stops = []
            for stop in line.stops:
                s = stop.station
                stops.append({
                    "id": stop.id,
                    "station": StationRead(
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
                    ).model_dump(),
                    "stop_order": stop.stop_order,
                    "distance_from_start_km": stop.distance_from_start_km,
                    "travel_time_from_start_min": stop.travel_time_from_start_min,
                    "departure_time": stop.departure_time,
                    "arrival_time": stop.arrival_time,
                })
            result.append({
                "id": line.id,
                "name": line.name,
                "operator": line.operator,
                "mode": line.mode,
                "color": line.color,
                "description": line.description,
                "distance_km": line.distance_km,
                "schedule_info": line.schedule_info,
                "pricing_info": line.pricing_info,
                "is_active": line.is_active,
                "stops": stops,
            })
        return result
