"""Tests for Pydantic AI agent tool functions.

Tests directly call each tool function with a mock RunContext,
seeding test data in the DB and verifying the output models.
"""

import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic_ai import RunContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import TravelAgentDeps
from app.agents.tools import (
    EventSearchParams,
    TransportRouteParams,
    WilayaGuideParams,
    find_events,
    get_transport_route,
    get_wilaya_guide,
)
from app.models.event import Event
from app.models.poi import POI
from app.models.user import User
from app.models.wilaya import Wilaya
from app.models.wilaya_distance import WilayaDistance

pytestmark = pytest.mark.asyncio


def _make_ctx(db: AsyncSession) -> RunContext[TravelAgentDeps]:
    user = User(id=uuid.uuid4(), phone="+213555999999")
    deps = TravelAgentDeps(user=user, db=db)
    return MagicMock(spec=RunContext, deps=deps)


# ── get_wilaya_guide ──

class TestGetWilayaGuide:
    async def test_not_found(self, db: AsyncSession):
        ctx = _make_ctx(db)
        result = await get_wilaya_guide(ctx, WilayaGuideParams(wilaya_id=58))
        # Wilaya 58 is seeded in test DB but has no description field
        assert result.wilaya_id == 58
        assert result.total_pois == 0
        assert result.featured_pois == []

    async def test_empty_wilaya(self, db: AsyncSession):
        # Wilaya 1 exists from seed, but has no POIs
        ctx = _make_ctx(db)
        result = await get_wilaya_guide(ctx, WilayaGuideParams(wilaya_id=1))
        assert result.wilaya_id == 1
        assert result.wilaya_name == "Adrar"
        assert result.total_pois == 0
        assert result.total_featured == 0
        assert result.featured_pois == []

    async def test_with_pois(self, db: AsyncSession):
        # Seed POIs
        for i, (name, cat, featured) in enumerate([
            ("Mosquée d'Adrar", "religious", True),
            ("Marché d'Adrar", "market", False),
            ("Musée d'Adrar", "museum", False),
        ]):
            db.add(POI(
                name=name, category=cat, wilaya_id=1,
                is_featured=featured, featured_order=i if featured else None,
                description=f"A nice {cat} in Adrar",
            ))
        await db.commit()

        ctx = _make_ctx(db)
        result = await get_wilaya_guide(ctx, WilayaGuideParams(wilaya_id=1, top_per_category=5))
        assert result.wilaya_id == 1
        assert result.wilaya_name == "Adrar"
        assert result.total_pois == 3
        assert result.total_featured == 1
        assert len(result.featured_pois) == 1
        assert result.featured_pois[0].name == "Mosquée d'Adrar"
        assert result.featured_pois[0].category == "religious"
        assert len(result.categories) >= 1
        # Should have market and museum categories
        cat_names = {c.category for c in result.categories}
        assert "market" in cat_names
        assert "museum" in cat_names

    async def test_with_tips(self, db: AsyncSession):
        # Seed 60 POIs to trigger the "plan 2-3 days" tip
        for i in range(60):
            db.add(POI(name=f"POI {i}", category="other", wilaya_id=1))
        await db.commit()

        ctx = _make_ctx(db)
        result = await get_wilaya_guide(ctx, WilayaGuideParams(wilaya_id=1))
        assert any("2-3 days" in tip for tip in result.tips)


# ── get_transport_route ──

class TestGetTransportRoute:
    async def test_no_route_data(self, db: AsyncSession):
        ctx = _make_ctx(db)
        result = await get_transport_route(ctx, TransportRouteParams(origin_wilaya_id=1, dest_wilaya_id=2))
        assert len(result.options) == 0
        assert "No transport route data" in (result.best_recommendation or "")

    async def test_with_route_data(self, db: AsyncSession):
        # Seed a WilayaDistance row
        db.add(WilayaDistance(
            origin_wilaya_id=1, dest_wilaya_id=2,
            driving_distance_km=400.0, driving_time_minutes=300,
            road_classification="national",
            has_train_route=False, has_direct_flight=False,
        ))
        # Ensure both wilayas exist
        w1 = await db.get(Wilaya, 1)
        w2 = await db.get(Wilaya, 2)
        if not w1:
            db.add(Wilaya(id=1, name_ar="", name_en="Adrar", name_fr="Adrar"))
        if not w2:
            db.add(Wilaya(id=2, name_ar="", name_en="Chlef", name_fr="Chlef"))
        await db.commit()

        ctx = _make_ctx(db)
        result = await get_transport_route(ctx, TransportRouteParams(origin_wilaya_id=1, dest_wilaya_id=2))
        # Should have driving option (always available)
        assert len(result.options) >= 1
        modes = {o.mode for o in result.options}
        assert "driving" in modes
        assert result.driving_time_minutes == 300
        # Driving option has pricing with bus/shared_taxi/private_taxi
        driving_opt = next(o for o in result.options if o.mode == "driving")
        assert driving_opt.pricing is not None
        assert driving_opt.pricing["shared_taxi_per_person"] > 0

    async def test_same_wilaya(self, db: AsyncSession):
        ctx = _make_ctx(db)
        result = await get_transport_route(ctx, TransportRouteParams(origin_wilaya_id=1, dest_wilaya_id=1))
        assert len(result.options) == 0


# ── find_events ──

class TestFindEvents:
    async def seed_events(self, db: AsyncSession):
        events = [
            Event(title="Festival du Couscous", wilaya_id=1, category="cultural", month=7, description="Annual couscous festival", duration_days=3, is_recurring=True),
            Event(title="Date Festival", wilaya_id=1, category="food", month=10, description="Date harvest celebration", duration_days=2, is_recurring=True),
            Event(title="Régate d'Oran", wilaya_id=31, category="beach", month=6, description="Sailing regatta", duration_days=1, is_recurring=True),
        ]
        for e in events:
            db.add(e)
        await db.commit()

    async def test_all_events(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams())
        assert result.total == 3
        assert len(result.results) == 3

    async def test_filter_by_wilaya(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams(wilaya_id=1))
        assert result.total == 2
        titles = {r.title for r in result.results}
        assert "Festival du Couscous" in titles
        assert "Date Festival" in titles

    async def test_filter_by_category(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams(category="food"))
        assert result.total == 1
        assert result.results[0].title == "Date Festival"

    async def test_filter_by_month(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams(month=7))
        assert result.total == 1
        assert result.results[0].title == "Festival du Couscous"

    async def test_no_results(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams(wilaya_id=58))
        assert result.total == 0
        assert result.results == []

    async def test_event_fields(self, db: AsyncSession):
        await self.seed_events(db)
        ctx = _make_ctx(db)
        result = await find_events(ctx, EventSearchParams(category="cultural"))
        assert result.total == 1
        ev = result.results[0]
        assert ev.title == "Festival du Couscous"
        assert ev.category == "cultural"
        assert ev.month == 7
        assert ev.duration_days == 3
        assert ev.is_recurring is True
        assert "couscous" in (ev.description or "")
