import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experience import Experience
from app.models.poi import POI
from app.models.price_report import PriceReport
from app.models.review import Review
from app.models.trip import TripItem
from app.models.wilaya import Wilaya
from app.schemas.trip import (
    OptimizationSuggestion,
    TripBrief,
    TripBriefExperience,
    TripBriefPOI,
    TripItemRead,
)


@dataclass
class Coord:
    lat: float
    lng: float


def _haversine_km(a: Coord, b: Coord) -> float:
    R = 6371
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    ha = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(ha), math.sqrt(1 - ha))


def _walk_time_minutes(dist_km: float) -> int:
    return int(dist_km / 5 * 60)


_DEFAULT_POI_DURATION = 90
_DEFAULT_EXPERIENCE_DURATION = 180


class TripOptimizer:
    async def enrich_items(
        self, db: AsyncSession, items: list[TripItem]
    ) -> list[TripItemRead]:
        if not items:
            return []

        poi_ids = [i.item_id for i in items if i.item_type == "poi"]
        exp_ids = [i.item_id for i in items if i.item_type == "experience"]

        pois: dict[uuid.UUID, POI] = {}
        if poi_ids:
            rows = (await db.execute(select(POI).where(POI.id.in_(poi_ids)))).scalars().all()
            pois = {p.id: p for p in rows}

        exps: dict[uuid.UUID, Experience] = {}
        if exp_ids:
            rows = (await db.execute(select(Experience).where(Experience.id.in_(exp_ids)))).scalars().all()
            exps = {e.id: e for e in rows}

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
                base.estimated_duration_minutes = int(e.duration_hours * 60) if e.duration_hours else _DEFAULT_EXPERIENCE_DURATION
                base.estimated_cost_dzd = e.price_dzd or 0
            result.append(base)

        return result

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
        total_km = 0

        while remaining:
            current = sorted_items[-1]
            current_coord = Coord(current.latitude, current.longitude)
            nearest_idx = 0
            nearest_dist = float("inf")

            for i, candidate in enumerate(remaining):
                dist = _haversine_km(current_coord, Coord(candidate.latitude, candidate.longitude))
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_idx = i

            total_km += nearest_dist
            sorted_items.append(remaining.pop(nearest_idx))

        return sorted_items + without_coords, round(total_km, 1)

    async def detect_gaps(
        self, enriched: list[TripItemRead], day_start_hour: int = 9, day_end_hour: int = 18
    ) -> list[str]:
        if not enriched:
            return []

        available_minutes = (day_end_hour - day_start_hour) * 60
        used_minutes = 0
        for i, item in enumerate(enriched):
            duration = item.estimated_duration_minutes or _DEFAULT_POI_DURATION
            used_minutes += duration
            if i < len(enriched) - 1:
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
                await db.execute(
                    select(POI)
                    .where(POI.wilaya_id == wid, POI.id.notin_(existing_ids))
                    .limit(3)
                )
            ).scalars().all()
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

        top_pois = []
        for row in pois_rows:
            reviews_query = (
                await db.execute(
                    select(Review.overall_score).where(Review.poi_id == row.id)
                )
            )
            scores = [r[0] for r in reviews_query.all()]
            avg = round(sum(scores) / len(scores), 1) if scores else None

            transport_cost = None
            price_rows = (
                await db.execute(
                    select(PriceReport.price_dzd)
                    .where(
                        PriceReport.origin_wilaya_id == origin_wilaya_id,
                        PriceReport.dest_wilaya_id == wilaya_id,
                    )
                    .limit(5)
                )
            )
            prices = [r[0] for r in price_rows.all()]
            if prices:
                transport_cost = f"{min(prices):,.0f}–{max(prices):,.0f} DZD"

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
            await db.execute(
                select(Experience).where(
                    Experience.wilaya_id == wilaya_id,
                    Experience.status == "active",
                ).limit(3)
            )
        ).scalars().all()

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
        if top_pois and top_pois[0].estimated_transport_cost:
            transport_advice = (
                f"From Algiers: {top_pois[0].estimated_transport_cost}. "
                f"Check /prices/estimate for exact routes."
            )

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
