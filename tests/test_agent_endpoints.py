"""Tests for Pydantic AI travel agent endpoints.

Tests cover:
- Auth required (401)
- Graceful 503 when no API key configured
- Validation errors (422)
- Happy path with mocked agents (now return plain text strings)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_AGENT_ENDPOINTS = {
    "chat": "/api/v1/agent/chat",
    "plan-trip": "/api/v1/agent/plan-trip",
    "search": "/api/v1/agent/search",
}


def _mock_run_result(data_obj):
    """Create a mock Agent.run() return value."""
    m = MagicMock()
    m.output = data_obj
    m.data = data_obj
    return m


def _make_mock_agent(data_obj):
    """Create a mock pydantic_ai Agent that returns data_obj on .run()."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=_mock_run_result(data_obj))
    return agent


def _inject_mock(_client: AsyncClient, name: str, agent):
    """Inject a mock agent into app.state for the duration of the test."""
    from app.main import app

    original = getattr(app.state, name, None)
    setattr(app.state, name, agent)
    return original


# ── Chat endpoint tests ──


class TestChatEndpoint:
    ENDPOINT = _AGENT_ENDPOINTS["chat"]

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "hello"},
        )
        assert resp.status_code == 401

    async def test_503_when_no_agent(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 503
        assert "VLLM" in resp.json()["detail"] or "OPENROUTER" in resp.json()["detail"]

    async def test_422_on_empty_message(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_422_on_missing_message(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(self.ENDPOINT, json={}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_success(self, client: AsyncClient, auth_headers: dict[str, str]):
        original = _inject_mock(
            client, "travel_agent", _make_mock_agent("Algiers has the Great Mosque, built in 2019.")
        )
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "Tell me about Algiers"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "travel_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "Great Mosque" in data["reply"]
        assert data["links"] == []
        assert data["orchestrated"] is False
        assert data["intents"] == ["travel"]

    async def test_success_with_wilaya_filter(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        original = _inject_mock(
            client, "travel_agent", _make_mock_agent("Oran has a beautiful coastline.")
        )
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "Tell me about Oran", "wilaya_id": 31},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "travel_agent", original)

        assert resp.status_code == 200
        assert "Oran" in resp.json()["reply"]


# ── Plan-trip endpoint tests ──


class TestPlanTripEndpoint:
    ENDPOINT = _AGENT_ENDPOINTS["plan-trip"]

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            self.ENDPOINT,
            json={"destination": "Algiers", "duration_days": 3},
        )
        assert resp.status_code == 401

    async def test_503_when_no_agent(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"destination": "Algiers", "duration_days": 3},
            headers=auth_headers,
        )
        assert resp.status_code == 503

    async def test_422_invalid_duration(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"destination": "Algiers", "duration_days": 0},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_422_invalid_budget(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"destination": "Algiers", "duration_days": 3, "budget": "cheap"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_success(self, client: AsyncClient, auth_headers: dict[str, str]):
        original = _inject_mock(
            client,
            "itinerary_agent",
            _make_mock_agent(
                "3-day trip to Algiers (mid-range, ~25,000 DZD).\n"
                "Day 1: Visit the Kasbah, Lunch at El Djenina.\n"
                "Day 2: Grande Mosquée, Bardo Museum.\n"
                "Day 3: Sidi Fredj, Seafood dinner."
            ),
        )
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"destination": "Algiers", "duration_days": 3, "interests": "history, food"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "itinerary_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data
        assert isinstance(data["plan"], str)
        assert "Algiers" in data["plan"]
        assert "Kasbah" in data["plan"]
        assert data["links"] == []


# ── Search endpoint tests ──


class TestSearchEndpoint:
    ENDPOINT = _AGENT_ENDPOINTS["search"]

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            self.ENDPOINT,
            json={"query": "beaches in Algiers"},
        )
        assert resp.status_code == 401

    async def test_503_when_no_agent(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"query": "beaches in Algiers"},
            headers=auth_headers,
        )
        assert resp.status_code == 503

    async def test_422_on_empty_query(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"query": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_success(self, client: AsyncClient, auth_headers: dict[str, str]):
        original = _inject_mock(
            client,
            "search_agent",
            _make_mock_agent("Found Sablettes Beach and Hotel Oran in Oran."),
        )
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"query": "beaches and hotels in Oran"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "search_agent", original)

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "Oran" in data["reply"]
        assert data["links"] == []

    async def test_empty_results(self, client: AsyncClient, auth_headers: dict[str, str]):
        original = _inject_mock(
            client, "search_agent", _make_mock_agent("No results found for 'zzzzzxyznonexistent'.")
        )
        try:
            resp = await client.post(
                self.ENDPOINT,
                json={"query": "zzzzzxyznonexistent"},
                headers=auth_headers,
            )
        finally:
            _inject_mock(client, "search_agent", original)

        assert resp.status_code == 200
        assert "reply" in resp.json()
