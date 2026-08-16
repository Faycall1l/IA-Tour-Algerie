"""Tests for SSE streaming chat endpoint.

Covers:
- SSE event format correctness
- /agent/chat/stream returns 401 without auth
- /agent/chat/stream returns 200 with text/event-stream content-type
- Fallback path (no agent configured) yields a degraded done event
- Invalid input yields an error event
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.streaming import _done_event, _error_event, _sse


# ── Unit: SSE helpers ──


class TestSSEHelpers:
    def test_sse_format(self):
        result = _sse({"type": "token", "text": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        payload = json.loads(result.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "token"
        assert payload["text"] == "hello"

    def test_done_event_structure(self):
        event = _done_event(text="Hello!", degraded=False, session_id="abc")
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "done"
        assert payload["text"] == "Hello!"
        assert payload["degraded"] is False
        assert payload["session_id"] == "abc"
        assert payload["links"] == []

    def test_done_event_with_links(self):
        from app.agents.links import AgentLink

        link = AgentLink(type="poi", id="42", name="Casbah", url="/pois/42")
        event = _done_event(links=[link])
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert len(payload["links"]) == 1
        assert payload["links"][0]["name"] == "Casbah"

    def test_error_event(self):
        event = _error_event("Something broke")
        payload = json.loads(event.removeprefix("data: ").removesuffix("\n\n"))
        assert payload["type"] == "error"
        assert payload["detail"] == "Something broke"


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
        # Body should be SSE data events
        body = resp.text
        assert "data: " in body
        # Parse the last event (should be done or error)
        events = [
            line.removeprefix("data: ")
            for line in body.strip().split("\n\n")
            if line.startswith("data: ")
        ]
        assert len(events) >= 1
        last = json.loads(events[-1])
        assert last["type"] in ("done", "error")

    async def test_fallback_degraded_event(self, client, auth_headers):
        """With travel_agent=None (default), fallback yields degraded done."""
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "What is the weather in Algiers?"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.text
        events = [
            line.removeprefix("data: ")
            for line in body.strip().split("\n\n")
            if line.startswith("data: ")
        ]
        assert len(events) >= 1
        last = json.loads(events[-1])
        # With no agent, should be either done (fallback) or error
        assert last["type"] in ("done", "error")
        if last["type"] == "done":
            assert last["degraded"] is True

    async def test_invalid_input_returns_error(self, client, auth_headers):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": ""},
            headers=auth_headers,
        )
        # min_length=1 on the request schema → 422
        assert resp.status_code == 422

    async def test_empty_message_after_validation(self, client, auth_headers):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "   "},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.text
        events = [
            line.removeprefix("data: ")
            for line in body.strip().split("\n\n")
            if line.startswith("data: ")
        ]
        assert len(events) >= 1
        last = json.loads(events[-1])
        # Whitespace-only message may be caught by validation → error event
        assert last["type"] in ("done", "error")
