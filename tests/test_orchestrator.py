"""Tests for the multi-agent orchestrator: intent routing, composing, and the
``/agent/chat`` orchestrated flow.

Covers:
- detect_intents: single-specialist routing, multi-intent routing, greeting → travel
- compose_replies: dedupe, section labels, per-section and total caps
- merge_links: dedupe across sections by (type, id), cap
- Endpoint: single-intent query short-circuits (orchestrated=False)
- Endpoint: multi-intent query composes mocked specialist replies (orchestrated=True)
- Endpoint: specialist failure degrades gracefully (keeps the other sections)
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.orchestrator import (
    Section,
    compose_replies,
    detect_intents,
    merge_links,
)

pytestmark = pytest.mark.asyncio


# ── Intent router ──


class TestDetectIntents:
    def test_greeting_is_travel_only(self):
        assert detect_intents("hello there") == ["travel"]

    def test_planning_query_routes_to_itinerary(self):
        assert "itinerary" in detect_intents("plan a 3 day trip to Oran")
        assert detect_intents("plan a 3 day trip to Oran")[0] == "itinerary"

    def test_transport_query(self):
        assert "transport" in detect_intents("how do I get to Djanet from Algiers")

    def test_events_query(self):
        assert "events" in detect_intents("are there any festivals in Constantine in June")

    def test_search_query(self):
        assert "search" in detect_intents("best beaches in Algiers")
        assert "search" in detect_intents("where can I find a good hotel in Oran")

    def test_multi_intent_message(self):
        intents = detect_intents("how do I get to Timgad and what festivals are in Batna")
        assert intents.index("transport") < intents.index("travel")
        assert "events" in intents

    def test_order_puts_travel_last(self):
        assert detect_intents("plan 3 days in Oran and get there by train")[-1] == "travel"

    def test_empty_message(self):
        assert detect_intents("") == ["travel"]


# ── Composer ──


class TestComposer:
    def _sec(self, label, text, degraded=False):
        return Section(label=label, text=text, degraded=degraded)

    def test_single_section(self):
        out = compose_replies([self._sec("Overview", "Hello Algiers")])
        assert "Hello Algiers" in out

    def test_sections_are_labelled(self):
        out = compose_replies(
            [
                self._sec("Overview", "General info"),
                self._sec("Getting there", "Take the train."),
            ]
        )
        assert "## Overview" in out
        assert "## Getting there" in out
        assert out.index("## Overview") < out.index("## Getting there")

    def test_dedupe_identical_sections(self):
        out = compose_replies(
            [
                self._sec("Overview", "Same text"),
                self._sec("Getting there", "Same text"),
            ]
        )
        assert out.count("Same text") == 1

    def test_empty_and_blank_sections_skipped(self):
        out = compose_replies([self._sec("Overview", ""), self._sec("Travel", "   ")])
        assert out == ""

    def test_section_capped(self):
        long = "x" * 5000
        out = compose_replies([self._sec("Overview", long)])
        assert len(out) < 5000
        assert out.endswith("[…]")

    def test_total_capped(self):
        sections = [self._sec(str(i), "y" * 4000) for i in range(5)]
        out = compose_replies(sections)
        assert len(out) < 10000


class TestMergeLinks:
    def test_dedupe_by_type_and_id(self):
        from app.agents.links import AgentLink

        a = AgentLink(type="poi", id="1", name="X", url="/pois/1", wilaya_id=16)
        b = AgentLink(type="poi", id="1", name="X", url="/pois/1", wilaya_id=16)
        c = AgentLink(type="event", id="2", name="Y", url="/events/2", wilaya_id=16)
        merged = merge_links(
            [Section("Overview", "a", links=[a, b]), Section("Events", "b", links=[c])]
        )
        assert len(merged) == 2

    def test_capped_at_eight(self):
        from app.agents.links import AgentLink

        links = [
            AgentLink(type="poi", id=str(i), name="X", url=f"/pois/{i}", wilaya_id=16)
            for i in range(12)
        ]
        assert len(merge_links([Section("Overview", "a", links=links)])) == 8


# ── Endpoint flow ──


def _make_mock_agent(data_obj):
    m = MagicMock()
    m.output = data_obj
    m.data = data_obj
    agent = MagicMock()
    agent.run = AsyncMock(return_value=m)
    return agent


def _set_state(name: str, agent):
    from app.main import app

    original = getattr(app.state, name, None)
    if agent is None:
        with contextlib.suppress(AttributeError, KeyError):
            delattr(app.state, name)
    else:
        setattr(app.state, name, agent)
    return original


class TestOrchestratedChat:
    ENDPOINT = "/api/v1/agent/chat"

    async def test_single_specialist_routes_to_it(self, client, auth_headers):
        saved = _set_state("search_agent", _make_mock_agent("Found 3 great beaches."))
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "best beaches in Algiers"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "Found 3 great beaches." in data["reply"]
            assert data["orchestrated"] is False
            assert "search" in data["intents"]
        finally:
            _set_state("search_agent", saved)

    async def test_multi_intent_composes_replies(self, client, auth_headers):
        for name, text in [
            ("travel_agent", "General overview text."),
            ("transport_agent", "Train option details."),
            ("events_agent", "Festival details."),
        ]:
            _set_state(name, _make_mock_agent(text))
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "how do I get to Constantine and what's on there in June?"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["orchestrated"] is True
            assert data["reply"].count("## ") >= 2
            assert "General overview text." in data["reply"]
            assert "Train option details." in data["reply"]
            assert "Festival details." in data["reply"]
            assert "transport" in data["intents"]
            assert "events" in data["intents"]
        finally:
            for name in ("travel_agent", "transport_agent", "events_agent"):
                _set_state(name, None)

    async def test_specialist_failure_keeps_other_sections(self, client, auth_headers):
        _set_state("travel_agent", _make_mock_agent("Overview survives."))
        _set_state("events_agent", None)
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "how do I get to Algiers and what festival is in June?"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "Overview survives." in data["reply"]
            assert data["orchestrated"] is True
        finally:
            for name in ("travel_agent", "events_agent"):
                _set_state(name, None)

    async def test_all_specialists_fail_returns_503(self, client, auth_headers):
        _set_state("travel_agent", None)
        _set_state("transport_agent", None)
        _set_state("itinerary_agent", None)
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "plan a week away and travel by train"},
            headers=auth_headers,
        )
        assert resp.status_code == 503
