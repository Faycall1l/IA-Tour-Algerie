from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wilaya_distance import WilayaDistance

DZD_PER_KM: dict[str, float] = {
    "bus": 6.0,
    "shared_taxi": 10.0,
    "train": 5.0,
    "private_taxi": 20.0,
    "plane": 14.0,
    "ferry": 8.0,
}

FLAT_COST: dict[str, float] = {
    "metro": 50.0,
    "tram": 40.0,
    "cablecar": 30.0,
    "plane": 12000.0,
    "ferry": 5000.0,
}


@dataclass
class TransportRoute:
    origin_wilaya_id: int
    dest_wilaya_id: int
    driving_distance_km: float
    driving_time_minutes: int
    road_classification: str
    has_train_route: bool
    has_direct_flight: bool

    def estimate_bus_cost(self) -> float:
        return round(self.driving_distance_km * DZD_PER_KM["bus"], -1)

    def estimate_shared_taxi_cost(self) -> float:
        return round(self.driving_distance_km * DZD_PER_KM["shared_taxi"], -1)

    def estimate_train_cost(self) -> float | None:
        if not self.has_train_route:
            return None
        return round(self.driving_distance_km * DZD_PER_KM["train"], -1)

    def estimate_private_taxi_cost(self) -> float:
        return round(self.driving_distance_km * DZD_PER_KM["private_taxi"], -1)

    def estimate_shared_taxi_cost_per_person(self) -> float:
        return round(self.estimate_shared_taxi_cost() / 4, -1)

    def estimate_plane_cost(self) -> float | None:
        if not self.has_direct_flight:
            return None
        dist_cost = round(self.driving_distance_km * DZD_PER_KM["plane"], -2)
        return max(dist_cost, FLAT_COST["plane"])

    def estimate_ferry_cost(self) -> float | None:
        if not self.origin_wilaya_id == 16 and not (self.origin_wilaya_id == 31 or self.dest_wilaya_id in (16, 31)):
            return None
        dist_cost = round(self.driving_distance_km * DZD_PER_KM["ferry"], -2)
        return max(dist_cost, FLAT_COST["ferry"])

    def travel_time_label(self) -> str:
        h, m = divmod(self.driving_time_minutes, 60)
        if h == 0:
            return f"{m}min"
        return f"{h}h{m:02d}" if m else f"{h}h"


class TransportService:
    def __init__(self) -> None:
        self._cache: dict[tuple[int, int], TransportRoute] = {}

    async def get_route(
        self, db: AsyncSession, origin_id: int, dest_id: int
    ) -> TransportRoute | None:
        if origin_id == dest_id:
            return None
        a, b = (origin_id, dest_id) if origin_id < dest_id else (dest_id, origin_id)
        cache_key = (a, b)
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = await db.execute(
            select(WilayaDistance).where(
                WilayaDistance.origin_wilaya_id == a,
                WilayaDistance.dest_wilaya_id == b,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        route = TransportRoute(
            origin_wilaya_id=a,
            dest_wilaya_id=b,
            driving_distance_km=row.driving_distance_km,
            driving_time_minutes=row.driving_time_minutes,
            road_classification=row.road_classification,
            has_train_route=row.has_train_route,
            has_direct_flight=row.has_direct_flight,
        )
        self._cache[cache_key] = route
        return route

    async def get_multiple_routes(
        self, db: AsyncSession, pairs: list[tuple[int, int]]
    ) -> dict[tuple[int, int], TransportRoute | None]:
        results: dict[tuple[int, int], TransportRoute | None] = {}
        for origin_id, dest_id in pairs:
            results[(origin_id, dest_id)] = await self.get_route(db, origin_id, dest_id)
        return results

    def clear_cache(self) -> None:
        self._cache.clear()
