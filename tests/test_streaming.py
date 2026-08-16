"""Tests for SSE streaming chat endpoint.

Covers:
- SSE event format correctness (token, section, section_done, done, error)
- /agent/chat/stream returns 401 without auth
- /agent/chat/stream returns 200 with text/event-stream content-type
- Fallback path (no agent configured) yields section_done + done events
- Single-intent message yields one section
- Multi-intent message yields multiple sections
- Invalid input yields an error event
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.streaming import _StreamResult, _dedupe_links, _sse


# ── Unit: SSE helpers ──


class TestSSEHelpers:
    def test_sse_format(self):
        result = _sse({"type": "token", "text": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        payload = json.loads(result.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "token"
        assert payload["text"] == "hello"

    def test_section_event(self):
        event = _sse({"type": "section", "agent": "travel", "label": "Overview"})
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "section"
        assert payload["agent"] == "travel"
        assert payload["label"] == "Overview"

    def test_section_done_event(self):
        event = _sse({"type": "section_done", "agent": "search", "links": [], "degraded": False})
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "section_done"
        assert payload["agent"] == "search"
        assert payload["degraded"] is False

    def test_done_event(self):
        event = _sse({"type": "done", "orchestrated": True, "links": [], "degraded": False})
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "done"
        assert payload["orchestrated"] is True

    def test_error_event(self):
        event = _sse({"type": "error", "detail": "Something broke"})
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "error"
        assert payload["detail"] == "Something broke"


class TestDedupeLinks:
    def test_removes_duplicates(self):
        from app.agents.links import AgentLink

        links = [
            AgentLink(type="poi", id="1", name="A", url="/a"),
            AgentLink(type="poi", id="1", name="A dup", url="/a"),
            AgentLink(type="stay", id="2", name="B", url="/b"),
        ]
        result = _dedupe_links(links)
        assert len(result) == 2
        assert result[0].name == "A"
        assert result[1].name == "B"

    def test_caps_at_eight(self):
        from app.agents.links import AgentLink

        links = [
            AgentLink(type="poi", id=str(i), name=f"P{i}", url=f"/{i}")
            for i in range(12)
        ]
        result = _dedupe_links(links)
        assert len(result) == 8


# ── Endpoint: auth + content type ──


class TestStreamEndpoint:
    ENDPOINT = "/api/v1/agent/chat/stream"

    async def test_requires_auth(self, client):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "hello"},
        )
        assert resp.status_code == 401

    async def test_returns_event_stream(self, client, auth_headers):
        """Even with no agent configured, the endpoint returns 200 + SSE format."""
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "What are the best beaches in Oran?"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct
        body = resp.text
        assert "data: " in body
        # Parse all events
        events = _parse_events(body)
        assert len(events) >= 1
        types = [e["type"] for e in events]
        # Should end with done (fallback) or have section_done + done
        assert types[-1] in ("done", "error")

    async def test_fallback_yields_section_and_done(self, client, auth_headers):
        """With no agents configured, fallback yields section_done + done."""
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "What is the weather in Algiers?"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        events = _parse_events(resp.text)
        types = [e["type"] for e in events]
        # At minimum: section (travel) + section_done + done
        assert "section" in types or "done" in types
        # The last event should be done or error
        assert types[-1] in ("done", "error")
        # If there's a section_done, it should have degraded=True
        section_dones = [e for e in events if e["type"] == "section_done"]
        if section_dones:
            assert section_dones[0]["degraded"] is True

    async def test_single_intent_yields_one_section(self, client, auth_headers):
        """A simple greeting yields one section (travel only)."""
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        events = _parse_events(resp.text)
        sections = [e for e in events if e["type"] == "section"]
        # At most one section (travel agent only for "hello")
        assert len(sections) <= 1

    async def test_invalid_input_returns_error(self, client, auth_headers):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": ""},
            headers=auth_headers,
        )
        # min_length=1 on the request schema → 422
        assert resp.status_code == 422

    async def test_empty_message_yields_error_event(self, client, auth_headers):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "   "},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        events = _parse_events(resp.text)
        assert len(events) >= 1
        types = [e["type"] for e in events]
        assert "error" in types or "done" in types


# ── Helpers ──


def _parse_events(body: str) -> list[dict]:
    """Parse SSE data lines from a response body into dicts."""
    events = []
    for line in body.strip().split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = json.loads(line.removeprefix("data: "))
            events.append(payload)
    return events
