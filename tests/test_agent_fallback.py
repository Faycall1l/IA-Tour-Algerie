"""Tests for the rule-based degradation fallback responder.

Covers:
- Pure helper units: text folding, alias removal, category/month/operator
  intent detection, keyword matching
- attempt_fallback against the real test DB: wilaya guide, POI/stay/experience
  search, events, operator contacts, transport route
- Conservative behaviour: no match / itinerary → None (falls through to 503)
- Endpoint integration: no-agent and breaker-open requests degrade to 200
  with `degraded: true` + `X-Agent-Degraded` header when the fallback can
  answer, and still 503 when it cannot
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.deps import TravelAgentDeps
from app.agents.fallback import (
    _detect_event_category,
    _detect_month,
    _detect_poi_category,
    _fold,
    _has_keywords,
    _has_operator_intent,
    _has_transport_intent,
    _ordered_route_wilayas,
    _remove_alias,
    attempt_fallback,
)
from app.agents.tools import (
    OperatorContactInfo,
    TransportModeOption,
    TransportRouteResult,
)
from httpx import AsyncClient


def _deps(db, user):
    return TravelAgentDeps(user=user, db=db)


async def _seed_catalog(db, user):
    """Seed one of everything the fallback can answer with."""
    from app.models.event import Event
    from app.models.experience import Experience
    from app.models.poi import POI
    from app.models.stay import Stay

    db.add(
        POI(
            name="Plage des Sablettes",
            category="beach",
            wilaya_id=16,
            latitude=36.81,
            longitude=3.16,
            description="Sandy beach on the Algiers bay with family facilities.",
            price_level="Free",
            suggested_duration_min=60,
        )
    )
    db.add(
        Stay(
            provider_id=user.id,
            name="Hotel Ibis Oran",
            property_type="hotel",
            wilaya_id=31,
            price_per_night_dzd=6500.0,
            description="Centrally located hotel in Oran.",
        )
    )
    db.add(
        Event(
            title="Yennayer Festival",
            wilaya_id=15,
            category="cultural",
            month=1,
            description="Berber new year celebrations in the Kabylie region.",
            duration_days=2,
            is_recurring=True,
        )
    )
    db.add(
        Experience(
            provider_id=user.id,
            title="Kabyle Hiking Tour",
            category="hiking",
            wilaya_id=15,
            status="active",
            price_dzd=4500.0,
            duration_hours=6.0,
            description="Guided hiking tour through the Djurdjura mountains.",
        )
    )
    await db.commit()


# ── Pure helper units ──


class TestHelpers:
    def test_fold_strips_accents_and_case(self):
        assert _fold("Béjaïa, Sétif") == "bejaia setif"
        assert _fold("  ORAN  ") == "oran"
        assert _fold("musée") == "musee"

    def test_remove_alias_whole_word_only(self):
        assert _remove_alias("beaches in algiers", "algiers") == "beaches in"
        assert _remove_alias("oran", "oran") == ""

    def test_detect_poi_category(self):
        assert _detect_poi_category("best beaches near Oran") == "beach"
        assert _detect_poi_category("museums in Constantine") == "museum"
        assert _detect_poi_category("roman ruins") == "historical"
        assert _detect_poi_category("hello there") is None

    def test_detect_event_category_and_month(self):
        assert _detect_event_category("music concert") == "music"
        assert _detect_event_category("food festival") == "food"
        assert _detect_month("in June") == 6
        assert _detect_month("en juillet") == 7
        assert _detect_month("random") is None

    def test_keyword_matching(self):
        assert _has_keywords("hotels in oran", "hotel") is True
        assert _has_keywords("hotels in oran", "restaurant") is False
        assert _has_keywords("where to stay", "stay") is True

    def test_operator_intent(self):
        assert _has_operator_intent("SNTF phone number") is True
        assert _has_operator_intent("air algerie contact") is True
        assert _has_operator_intent("where can i call") is True
        assert _has_operator_intent("hello") is False

    def test_transport_intent(self):
        for q in (
            "how do i get to djanet from algiers",
            "bus from oran to tlemcen",
            "flight to tammanrasset",
            "what is the best way to reach timimoun",
        ):
            assert _has_transport_intent(q), q
        for q in (
            "best hotel in djanet",
            "restaurants in algiers",
            "what to see in oran",
        ):
            assert not _has_transport_intent(q), q


# ── attempt_fallback (real test DB) ──


class TestTransportFallback:
    pytestmark = pytest.mark.asyncio

    async def test_ordered_route_wilayas_honors_from_to(self, db, test_user):
        from sqlalchemy import text

        djanet = (
            await db.execute(text("SELECT id FROM wilayas WHERE name_en = 'Djanet'"))
        ).scalar()
        deps = _deps(db, test_user)
        origin, dest = await _ordered_route_wilayas(
            deps, "how do i get to djanet from algiers", None, None
        )
        assert origin == 16  # Algiers
        assert dest == djanet
        origin, dest = await _ordered_route_wilayas(
            deps, "travel from algiers to djanet", None, None
        )
        assert origin == 16
        assert dest == djanet
        assert await _ordered_route_wilayas(deps, "djanet only", None, None) is None

    async def test_travel_fallback_routes_transport_queries(self, db, test_user, monkeypatch):
        """A 'get to X from Y' query must hit transport, not the wilaya guide."""
        from app.agents import fallback
        from sqlalchemy import text

        djanet = (
            await db.execute(text("SELECT id FROM wilayas WHERE name_en = 'Djanet'"))
        ).scalar()

        async def fake_route(_deps, fw, tw):
            return f"FAKE ROUTE {fw}->{tw}"

        monkeypatch.setattr(fallback, "_handle_transport_route", fake_route)
        reply = await attempt_fallback(
            "travel_agent", "How do I get to Djanet from Algiers?", _deps(db, test_user)
        )
        assert reply == f"FAKE ROUTE 16->{djanet}"


class TestAttemptFallback:
    pytestmark = pytest.mark.asyncio

    async def test_wilaya_guide_travel(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback(
            "travel_agent", "what to see in Algiers?", _deps(db, test_user)
        )
        assert reply is not None
        assert "travel guide" in reply
        assert "Sablettes" in reply

    async def test_poi_search(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback("travel_agent", "beaches in Algiers", _deps(db, test_user))
        assert reply is not None
        assert "Sablettes" in reply
        assert "Offline" in reply

    async def test_stay_search(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback("travel_agent", "hotels in Oran", _deps(db, test_user))
        assert reply is not None
        assert "Ibis" in reply
        assert "DZD/night" in reply

    async def test_search_agent_experience(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback(
            "search_agent", "hiking tours in Tizi Ouzou", _deps(db, test_user)
        )
        assert reply is not None
        assert "Hiking Tour" in reply

    async def test_search_agent_wilaya_guide_fallback(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback("search_agent", "Oran", _deps(db, test_user))
        assert reply is not None
        assert "Ibis" in reply

    async def test_events(self, db, test_user):
        await _seed_catalog(db, test_user)
        reply = await attempt_fallback(
            "events_agent", "festivals in Tizi Ouzou in January", _deps(db, test_user)
        )
        assert reply is not None
        assert "Yennayer" in reply

    async def test_operator_contacts(self, db, test_user):
        from app.models import TransportOperator

        db.add(
            TransportOperator(
                name="SNTF",
                mode="train",
                phone="+213211711510",
                is_active=True,
            )
        )
        await db.commit()
        reply = await attempt_fallback(
            "travel_agent", "what is the SNTF phone number?", _deps(db, test_user)
        )
        assert reply is not None
        assert "SNTF" in reply
        assert "+213211711510" in reply

    async def test_transport_route_from_message(self, db, test_user, monkeypatch):
        from app.agents import fallback as fb

        async def fake_route(_ctx, params):
            assert (params.origin_wilaya_id, params.dest_wilaya_id) == (16, 31)
            return TransportRouteResult(
                origin_wilaya="Algiers",
                dest_wilaya="Oran",
                origin_wilaya_id=16,
                dest_wilaya_id=31,
                driving_distance_km=430.0,
                driving_time_minutes=330,
                options=[
                    TransportModeOption(
                        mode="train",
                        line_name="Algiers-Oran",
                        operator="SNTF",
                        cost_dzd=2500.0,
                        duration_min=180,
                        contacts=[
                            OperatorContactInfo(name="SNTF", mode="train", phone="+213211711510")
                        ],
                    ),
                ],
                best_recommendation="Cheapest: train at 2500 DZD",
            )

        monkeypatch.setattr(fb, "get_transport_route", fake_route)
        reply = await attempt_fallback(
            "transport_agent", "how to get from Algiers to Oran", _deps(db, test_user)
        )
        assert reply is not None
        assert "Algiers" in reply and "Oran" in reply
        assert "SNTF" in reply
        assert "+213211711510" in reply

    async def test_transport_route_from_explicit_ids(self, db, test_user, monkeypatch):
        from app.agents import fallback as fb

        calls = {}

        async def fake_route(_ctx, params):
            calls["ids"] = (params.origin_wilaya_id, params.dest_wilaya_id)
            return TransportRouteResult(
                origin_wilaya="Algiers",
                dest_wilaya="Oran",
                origin_wilaya_id=16,
                dest_wilaya_id=31,
                options=[TransportModeOption(mode="taxi", cost_dzd=1500.0, duration_min=270)],
                best_recommendation="Cheapest: taxi at 1500 DZD",
            )

        monkeypatch.setattr(fb, "get_transport_route", fake_route)
        reply = await attempt_fallback(
            "transport_agent",
            "how do I get between these",
            _deps(db, test_user),
            from_wilaya=16,
            to_wilaya=31,
        )
        assert reply is not None
        assert calls["ids"] == (16, 31)
        assert "taxi" in reply

    async def test_no_match_returns_none(self, db, test_user):
        assert await attempt_fallback("travel_agent", "hello", _deps(db, test_user)) is None
        assert await attempt_fallback("travel_agent", "zzzz qqqqq", _deps(db, test_user)) is None

    async def test_itinerary_never_falls_back(self, db, test_user):
        reply = await attempt_fallback("itinerary_agent", "plan Algiers", _deps(db, test_user))
        assert reply is None

    async def test_empty_message_returns_none(self, db, test_user):
        assert await attempt_fallback("travel_agent", "   ", _deps(db, test_user)) is None


# ── Endpoint integration ──

_AGENT_STATE_KEYS = (
    "travel_agent",
    "search_agent",
    "transport_agent",
    "events_agent",
    "itinerary_agent",
)


def _clear_agent_state(app):
    """Snapshot and remove the 5 agent singletons from app.state.

    The app object is a module-level singleton shared across the whole suite, so
    earlier test files may leave a travel_agent behind — that would make the
    "no agent" tests hit the LLM path instead of the fallback. Restores state on
    teardown via the returned callable.
    """
    saved = {name: getattr(app.state, name, None) for name in _AGENT_STATE_KEYS}
    for name in _AGENT_STATE_KEYS:
        if hasattr(app.state, name):
            delattr(app.state, name)

    def restore():
        for name, value in saved.items():
            if value is None:
                if hasattr(app.state, name):
                    delattr(app.state, name)
            else:
                setattr(app.state, name, value)

    return restore


class TestEndpointFallback:
    pytestmark = pytest.mark.asyncio
    ENDPOINT = "/api/v1/agent/chat"

    async def test_no_agent_degrades_to_fallback(
        self, client: AsyncClient, auth_headers, db, test_user
    ):
        from app.main import app
        from app.models.stay import Stay

        restore = _clear_agent_state(app)
        try:
            db.add(
                Stay(
                    provider_id=test_user.id,
                    name="Hotel Ibis Oran",
                    property_type="hotel",
                    wilaya_id=31,
                    price_per_night_dzd=6500.0,
                )
            )
            await db.commit()

            resp = await client.post(
                self.ENDPOINT, json={"message": "hotels in Oran"}, headers=auth_headers
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["degraded"] is True
            assert "Ibis" in data["reply"]
            assert resp.headers.get("x-agent-degraded") == "rule-based-fallback"
        finally:
            restore()

    async def test_no_agent_no_match_503(self, client: AsyncClient, auth_headers):
        from app.main import app

        restore = _clear_agent_state(app)
        try:
            resp = await client.post(self.ENDPOINT, json={"message": "hello"}, headers=auth_headers)
            assert resp.status_code == 503
            assert "VLLM" in resp.json()["detail"]
        finally:
            restore()

    async def test_breaker_open_degrades_to_fallback(
        self, client: AsyncClient, auth_headers, db, test_user
    ):
        from app.agents.harness import get_circuit_breaker
        from app.main import app
        from app.models.stay import Stay

        db.add(
            Stay(
                provider_id=test_user.id,
                name="Hotel Panorama Tlemcen",
                property_type="hotel",
                wilaya_id=13,
                price_per_night_dzd=8000.0,
            )
        )
        await db.commit()

        cb = get_circuit_breaker("travel_agent")
        orig_threshold = cb.failure_threshold
        orig_count = cb.failure_count
        orig_state = cb.state
        cb.failure_threshold = 1
        cb.record_failure()
        assert not cb.allow_request()

        agent = MagicMock()
        agent.run = AsyncMock()
        original = getattr(app.state, "travel_agent", None)
        app.state.travel_agent = agent
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "hotels in Tlemcen"},
                headers=auth_headers,
            )
        finally:
            cb.failure_threshold = orig_threshold
            cb.failure_count = orig_count
            cb.state = orig_state  # restore state too — OPEN must not leak across tests
            app.state.travel_agent = original

        assert resp.status_code == 200
        data = resp.json()
        assert data["degraded"] is True
        assert "Panorama" in data["reply"]
        agent.run.assert_not_awaited()
