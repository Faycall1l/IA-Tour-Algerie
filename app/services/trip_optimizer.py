import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experience import Experience
from app.models.poi import POI
from app.models.review import Review
from app.models.stay import Stay
from app.models.trip import TripItem
from app.models.wilaya import Wilaya
from app.schemas.trip import (
    OptimizationSuggestion,
    TripBrief,
    TripBriefExperience,
    TripBriefPOI,
    TripItemRead,
)
from app.services.transit_routing import TransitRoutingService
from app.services.transport import TransportService


@dataclass
class Coord:
    lat: float
    lng: float


def _haversine_km(a: Coord, b: Coord) -> float:
    radius = 6371  # noqa: N806
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    ha = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(ha), math.sqrt(1 - ha))


def _walk_time_minutes(dist_km: float) -> int:
    return int(dist_km / 5 * 60)


_DEFAULT_POI_DURATION = 90
_DEFAULT_EXPERIENCE_DURATION = 180
_DEFAULT_STAY_DURATION = 720  # overnight ~12h
_DEFAULT_RESTAURANT_DURATION = 90
_DEFAULT_TRANSPORT_DURATION = 60


class TripOptimizer:
    def __init__(self, transit_routing: TransitRoutingService | None = None) -> None:
        self._transit_routing = transit_routing

    async def enrich_items(self, db: AsyncSession, items: list[TripItem]) -> list[TripItemRead]:
        if not items:
            return []

        poi_ids = [i.item_id for i in items if i.item_type == "poi"]
        exp_ids = [i.item_id for i in items if i.item_type == "experience"]
        stay_ids = [i.item_id for i in items if i.item_type == "stay"]

        pois: dict[uuid.UUID, POI] = {}
        if poi_ids:
            rows = (await db.execute(select(POI).where(POI.id.in_(poi_ids)))).scalars().all()
            pois = {p.id: p for p in rows}

        exps: dict[uuid.UUID, Experience] = {}
        if exp_ids:
            stmt = select(Experience).where(Experience.id.in_(exp_ids))
            rows = (await db.execute(stmt)).scalars().all()
            exps = {e.id: e for e in rows}

        stays: dict[uuid.UUID, Stay] = {}
        if stay_ids:
            rows = (await db.execute(select(Stay).where(Stay.id.in_(stay_ids)))).scalars().all()
            stays = {s.id: s for s in rows}

        result = []
        for item in items:
            base = TripItemRead.model_validate(item)
            if item.item_type == "poi" and item.item_id in pois:
                p = pois[item.item_id]
                base.item_name = p.name
                base.item_image = p.photo_url
                base.latitude = p.latitude
                base.longitude = p.longitude
                base.estimated_duration_minutes = _DEFAULT_POI_DURATION
                base.estimated_cost_dzd = p.entry_fee_dzd or 0
            elif item.item_type == "experience" and item.item_id in exps:
                e = exps[item.item_id]
                base.item_name = e.title
                base.item_image = e.photos[0] if e.photos else None
                base.latitude = e.meeting_point_lat
                base.longitude = e.meeting_point_lng
                base.estimated_duration_minutes = (
                    int(e.duration_hours * 60) if e.duration_hours else _DEFAULT_EXPERIENCE_DURATION
                )
                base.estimated_cost_dzd = e.price_dzd or 0
            elif item.item_type == "stay" and item.item_id in stays:
                s = stays[item.item_id]
                base.item_name = s.name
                base.item_image = s.photos[0] if s.photos else None
                base.latitude = s.latitude
                base.longitude = s.longitude
                base.estimated_duration_minutes = _DEFAULT_STAY_DURATION
                base.estimated_cost_dzd = s.price_per_night_dzd
            elif item.item_type == "restaurant":
                base.item_name = "Restaurant"
                base.estimated_duration_minutes = _DEFAULT_RESTAURANT_DURATION
            elif item.item_type == "transport":
                base.item_name = "Transport"
                base.estimated_duration_minutes = _DEFAULT_TRANSPORT_DURATION
            result.append(base)

        return result

    async def _travel_time_min(
        self, db: AsyncSession, a: TripItemRead, b: TripItemRead
    ) -> int | None:
        if not self._transit_routing:
            return None
        try:
            result = await self._transit_routing.find_route(
                db, a.latitude, a.longitude, b.latitude, b.longitude
            )
            if result and result.total_estimated_minutes:
                return result.total_estimated_minutes
        except Exception:
            pass
        return None

    async def optimize_day(
        self, db: AsyncSession, items: list[TripItem]
    ) -> tuple[list[TripItemRead], float]:
        enriched = await self.enrich_items(db, items)

        with_coords = [e for e in enriched if e.latitude is not None and e.longitude is not None]
        without_coords = [e for e in enriched if e.latitude is None or e.longitude is None]

        if not with_coords:
            return enriched, 0

        sorted_items = [with_coords[0]]
        remaining = list(with_coords[1:])
        total_cost = 0

        while remaining:
            current = sorted_items[-1]
            current_coord = Coord(current.latitude, current.longitude)
            nearest_idx = 0
            nearest_cost = float("inf")

            for i, candidate in enumerate(remaining):
                transit = await self._travel_time_min(db, current, candidate)
                if transit is not None:
                    cost = transit
                else:
                    cost = _haversine_km(current_coord, Coord(candidate.latitude, candidate.longitude))
                if cost < nearest_cost:
                    nearest_cost = cost
                    nearest_idx = i

            total_cost += nearest_cost
            sorted_items.append(remaining.pop(nearest_idx))

        return sorted_items + without_coords, round(total_cost, 1)

    async def detect_gaps(
        self, db: AsyncSession, enriched: list[TripItemRead],
        day_start_hour: int = 9, day_end_hour: int = 18
    ) -> list[str]:
        if not enriched:
            return []

        available_minutes = (day_end_hour - day_start_hour) * 60
        used_minutes = 0
        for i, item in enumerate(enriched):
            duration = item.estimated_duration_minutes or _DEFAULT_POI_DURATION
            used_minutes += duration
            if i < len(enriched) - 1:
                transit = await self._travel_time_min(db, enriched[i], enriched[i + 1])
                if transit is not None:
                    travel = transit
                else:
                    travel = _walk_time_minutes(
                        _haversine_km(
                            Coord(enriched[i].latitude or 0, enriched[i].longitude or 0),
                            Coord(enriched[i + 1].latitude or 0, enriched[i + 1].longitude or 0),
                        )
                    )
                used_minutes += travel

        gap_minutes = available_minutes - used_minutes
        if gap_minutes > 60:
            return [f"{gap_minutes} min free"]
        return []

    async def suggest_fillers(
        self,
        db: AsyncSession,
        trip_id: uuid.UUID,
        day_number: int,
        wilaya_ids: list[int],
        existing_ids: set[uuid.UUID],
    ) -> list[OptimizationSuggestion]:
        suggestions = []
        for wid in wilaya_ids:
            rows = (
                (
                    await db.execute(
                        select(POI)
                        .where(POI.wilaya_id == wid, POI.id.notin_(existing_ids))
                        .limit(3)
                    )
                )
                .scalars()
                .all()
            )
            for p in rows:
                suggestions.append(
                    OptimizationSuggestion(
                        item_id=p.id,
                        reason=f"Nearby: {p.name} ({p.category})",
                        action="add_to_trip",
                    )
                )
        return suggestions

    async def compute_budget(
        self, db: AsyncSession, items: list[TripItem]
    ) -> tuple[float, float | None]:
        enriched = await self.enrich_items(db, items)
        spent = sum(e.estimated_cost_dzd or 0 for e in enriched)
        return spent, spent


class TripBriefGenerator:
    def __init__(self, transport_service: TransportService | None = None) -> None:
        self._transport = transport_service or TransportService()

    async def generate(
        self,
        db: AsyncSession,
        wilaya_id: int,
        origin_wilaya_id: int = 1,
    ) -> TripBrief | None:
        wilaya = await db.get(Wilaya, wilaya_id)
        if not wilaya:
            return None

        pois_rows = (
            await db.execute(
                select(
                    POI.id,
                    POI.name,
                    POI.category,
                    POI.photo_url,
                    POI.latitude,
                    POI.longitude,
                )
                .where(POI.wilaya_id == wilaya_id)
                .limit(5)
            )
        ).all()

        poi_ids = [r.id for r in pois_rows]
        review_scores: dict[uuid.UUID, list[int]] = {}
        if poi_ids:
            review_rows = (
                await db.execute(
                    select(Review.poi_id, Review.overall_score).where(Review.poi_id.in_(poi_ids))
                )
            ).all()
            for pid, score in review_rows:
                review_scores.setdefault(pid, []).append(score)

        route = None
        if origin_wilaya_id != wilaya_id:
            route = await self._transport.get_route(db, origin_wilaya_id, wilaya_id)

        top_pois = []
        for row in pois_rows:
            scores = review_scores.get(row.id, [])
            avg = round(sum(scores) / len(scores), 1) if scores else None

            transport_cost = None
            if route:
                bus = route.estimate_bus_cost()
                taxi = route.estimate_shared_taxi_cost()
                label = route.travel_time_label()
                transport_cost = f"Bus ~{bus:,.0f} DZD | Taxi ~{taxi:,.0f} DZD ({label})"

            top_pois.append(
                TripBriefPOI(
                    id=row.id,
                    name=row.name,
                    category=row.category,
                    average_score=avg,
                    total_reviews=len(scores),
                    photo_url=row.photo_url,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    estimated_transport_cost=transport_cost,
                )
            )

        exp_rows = (
            (
                await db.execute(
                    select(Experience)
                    .where(
                        Experience.wilaya_id == wilaya_id,
                        Experience.status == "active",
                    )
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )

        top_experiences = [
            TripBriefExperience(
                id=e.id,
                title=e.title,
                category=e.category,
                price_dzd=e.price_dzd,
                duration_hours=e.duration_hours,
                provider_name=None,
            )
            for e in exp_rows
        ]

        transport_advice = None
        if route:
            label = route.travel_time_label()
            bus_cost = route.estimate_bus_cost()
            taxi_cost = route.estimate_shared_taxi_cost()
            transport_advice = (
                f"From Algiers: {route.driving_distance_km:.0f}km, ~{label} by car. "
                f"Bus ~{bus_cost:,.0f} DZD, shared taxi ~{taxi_cost:,.0f} DZD."
            )
            if route.has_train_route:
                train_cost = route.estimate_train_cost()
                if train_cost:
                    transport_advice += f" Train ~{train_cost:,.0f} DZD."
            if route.has_direct_flight:
                plane_cost = route.estimate_plane_cost()
                if plane_cost:
                    transport_advice += f" Flight ~{plane_cost:,.0f} DZD."

        tips = []
        if top_pois:
            tips.append(f"Most popular: {top_pois[0].name}")
            tips.append(f"{len(top_pois)} POIs and {len(top_experiences)} experiences available")

        return TripBrief(
            wilaya_id=wilaya_id,
            wilaya_name=wilaya.name_en,
            top_pois=top_pois,
            top_experiences=top_experiences,
            transport_advice=transport_advice,
            tips=tips,
        )
