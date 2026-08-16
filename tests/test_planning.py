"""Tests for plan → verify: structured itinerary output and verification.

Covers:
- render_trip_plan: deterministic markdown rendering of a TripPlan
- PlanVerification models: pydantic serialization
- render_verification: human-readable verification section
- verify_trip_plan against real test DB: real POI/stay found + fictional place flagged
- Endpoint: mocked itinerary agent returning TripPlan → verification present
- Endpoint: mocked itinerary agent returning str → verification None
- Edge: destination not resolvable → destination_found=False
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.planning import (
    PlanVerification,
    VerifiedDay,
    VerifiedEntry,
    render_trip_plan,
    render_verification,
    verify_trip_plan,
)
from app.agents.travel_agent import ItineraryDay, TripPlan
from sqlalchemy.ext.asyncio import AsyncSession

# ── Helpers ──


def _make_trip_plan(
    *,
    destination: str = "Algiers",
    duration_days: int = 2,
    budget_level: str = "mid-range",
    days: list[ItineraryDay] | None = None,
    key_attractions: list[str] | None = None,
    tips: list[str] | None = None,
) -> TripPlan:
    if days is None:
        days = [
            ItineraryDay(
                day=1,
                morning="Visit the Casbah d'Alger and the Musée National du Bardo",
                afternoon="Stroll through Jardin d'Essai Hamma",
                evening="Dinner in the Casbah area",
                meals=["Restaurant El Djazair"],
                accommodation="Hotel El-Djazair",
            ),
            ItineraryDay(
                day=2,
                morning="Explore the Monument des Martyrs",
                afternoon="Relax at Sablettes Beach",
                evening="Walk along Rue Didouche Mourad",
                meals=[],
                accommodation=None,
            ),
        ]
    return TripPlan(
        destination=destination,
        duration_days=duration_days,
        budget_level=budget_level,
        itinerary=days,
        key_attractions=key_attractions or ["Casbah d'Alger"],
        tips=tips or ["Bring water in summer"],
        estimated_budget_dzd=15000.0,
    )


def _mock_run_result(data_obj):
    m = MagicMock()
    m.output = data_obj
    m.data = data_obj
    return m


def _make_mock_agent(data_obj):
    agent = MagicMock()
    agent.run = AsyncMock(return_value=_mock_run_result(data_obj))
    return agent


def _inject_mock(_client, name: str, agent):
    from app.main import app

    original = getattr(app.state, name, None)
    setattr(app.state, name, agent)
    return original


# ── Unit: render_trip_plan ──


class TestRenderTripPlan:
    def test_contains_days(self):
        plan = _make_trip_plan()
        rendered = render_trip_plan(plan)
        assert "Algiers" in rendered
        assert "Day 1" in rendered
        assert "Day 2" in rendered
        assert "mid-range" in rendered

    def test_empty_itinerary(self):
        plan = _make_trip_plan(days=[], duration_days=1)
        rendered = render_trip_plan(plan)
        assert "Algiers" in rendered
        assert "Must-see" in rendered

    def test_meals_and_accommodation(self):
        days = [
            ItineraryDay(
                day=1,
                morning="A",
                afternoon="B",
                evening="C",
                meals=["Cafe X", "Restaurant Y"],
                accommodation="Hotel Z",
            ),
        ]
        plan = _make_trip_plan(days=days, duration_days=1)
        rendered = render_trip_plan(plan)
        assert "Cafe X" in rendered
        assert "Restaurant Y" in rendered
        assert "Hotel Z" in rendered


# ── Unit: render_verification ──


class TestRenderVerification:
    def test_found_and_missing(self):
        v = PlanVerification(
            destination="Algiers",
            destination_found=True,
            destination_wilaya_id=16,
            days=[
                VerifiedDay(
                    day=1,
                    entries=[
                        VerifiedEntry(
                            name="Casbah",
                            kind="poi",
                            found=True,
                            match_id="1",
                            match_name="Casbah d'Alger",
                        ),
                        VerifiedEntry(name="Lunar Palace", kind="poi", found=False),
                    ],
                ),
            ],
            found_count=1,
            missing_count=1,
            verified_ratio=0.5,
        )
        text = render_verification(v)
        assert "Casbah" in text
        assert "✓" in text
        assert "Lunar Palace" in text
        assert "✗" in text
        assert "1 of 2" in text
        assert "50%" in text

    def test_destination_not_found(self):
        v = PlanVerification(destination="Xanadu", destination_found=False)
        text = render_verification(v)
        assert "Xanadu" in text
        assert "not recognised" in text

    def test_empty_entries(self):
        v = PlanVerification(destination="Oran", destination_found=True, destination_wilaya_id=31)
        text = render_verification(v)
        assert "Oran" in text


# ── Unit: verify_trip_plan against real test DB ──


class TestVerifyTripPlan:
    @pytest.mark.asyncio
    async def test_real_poi_found_fictional_missing(self, db: AsyncSession):
        from app.models.poi import POI

        # Insert a real POI in Algiers (w16)
        poi = POI(
            name="Casbah d'Alger",
            name_en="Casbah of Algiers",
            category="historical",
            subtype="museum",
            wilaya_id=16,
            latitude=36.78,
            longitude=3.05,
            description="Historic casbah",
        )
        db.add(poi)
        await db.flush()

        plan = _make_trip_plan()
        verification = await verify_trip_plan(db, plan)

        assert verification.destination_found is True
        assert verification.destination_wilaya_id == 16

        # Collect all entry names
        all_entries = []
        for day in verification.days:
            all_entries.extend(day.entries)

        # Casbah d'Alger should be found (substring "casbah d alger" in the item)
        found_names = [e.name for e in all_entries if e.found]
        assert any("Casbah" in n for n in found_names), (
            f"Expected 'Casbah' in found, got {found_names}"
        )
        # "Lunar Palace" or "Sablettes Beach" are not in the DB
        assert verification.missing_count >= 1

    @pytest.mark.asyncio
    async def test_unrecognised_destination(self, db: AsyncSession):
        plan = _make_trip_plan(destination="Xanadu")
        verification = await verify_trip_plan(db, plan)
        assert verification.destination_found is False
        assert verification.destination_wilaya_id is None
        assert verification.missing_count >= 1


# ── Endpoint integration ──


class TestPlanTripEndpoint:
    ENDPOINT = "/api/v1/agent/plan-trip"

    async def test_structured_output_triggers_verification(
        self, client, auth_headers, db: AsyncSession
    ):
        from app.models.poi import POI

        # Ensure at least one real POI exists for Algiers in the test DB
        poi = POI(
            name="Casbah d'Alger",
            name_en="Casbah of Algiers",
            category="historical",
            subtype="museum",
            wilaya_id=16,
            latitude=36.78,
            longitude=3.05,
            description="Historic casbah",
        )
        db.add(poi)
        await db.flush()

        plan = _make_trip_plan()
        original = _inject_mock(client, "itinerary_agent", _make_mock_agent(plan))
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"destination": "Algiers", "duration_days": 2, "budget": "mid-range"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "itinerary_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        # The rendered plan text should contain the verification section
        assert "Verification" in data["plan"]
        # Structured verification should be present and well-formed
        verification = data.get("verification")
        assert verification is not None, "Expected structured verification in response"
        assert verification["destination"] == "Algiers"
        assert verification["destination_found"] is True
        assert isinstance(verification["days"], list)

    async def test_free_text_output_skips_verification(self, client, auth_headers):
        text_reply = "Here is your 3-day trip to Algiers with museums and beaches."
        original = _inject_mock(client, "itinerary_agent", _make_mock_agent(text_reply))
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"destination": "Algiers", "duration_days": 3, "budget": "mid-range"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "itinerary_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        # Free-text output should not trigger verification
        assert data.get("verification") is None
        # The reply should still contain the rendered text
        assert "Algiers" in data["plan"]

    async def test_unrecognised_destination_flags_not_found(self, client, auth_headers):
        plan = _make_trip_plan(destination="Xanadu")
        original = _inject_mock(client, "itinerary_agent", _make_mock_agent(plan))
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"destination": "Xanadu", "duration_days": 1, "budget": "budget"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "itinerary_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        verification = data.get("verification")
        assert verification is not None
        assert verification["destination_found"] is False
