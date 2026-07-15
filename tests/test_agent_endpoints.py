"""Tests for Pydantic AI travel agent endpoints.

Tests cover:
- Auth required (401)
- Graceful 503 when no API key configured
- Validation errors (422)
- Happy path with mocked agents
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.agents.travel_agent import ItineraryDay, TripPlan

pytestmark = pytest.mark.asyncio

_AGENT_ENDPOINTS = {
    "chat": "/api/v1/agent/chat",
    "plan-trip": "/api/v1/agent/plan-trip",
    "search": "/api/v1/agent/search",
}


def _mock_run_result(data_obj):
    """Create a mock Agent.run() return value."""
    m = MagicMock()
    m.data = data_obj
    return m


def _make_mock_agent(data_obj):
    """Create a mock pydantic_ai Agent that returns data_obj on .run()."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=_mock_run_result(data_obj))
    return agent


def _inject_mock(client: AsyncClient, name: str, agent):
    """Inject a mock agent onto app.state."""
    client._transport.app.state.__setattr__(name, agent)


# ── Chat endpoint tests ──

class TestChatEndpoint:
    ENDPOINT = _AGENT_ENDPOINTS["chat"]

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(self.ENDPOINT, json={"message": "hello"})
        assert resp.status_code == 401

    async def test_503_when_no_agent(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.post(
            self.ENDPOINT,
            json={"message": "hello"},
            headers=auth_headers,
        )
        assert resp.status_code == 503
        assert "OPENROUTER_API_KEY" in resp.json()["detail"]

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
        mock_data = MagicMock()
        mock_data.summary = "Algiers has the Great Mosque, built in 2019."
        mock_data.pois = []
        mock_data.stays = []
        mock_data.experiences = []
        _inject_mock(client, "travel_agent", _make_mock_agent(mock_data))

        resp = await client.post(
            self.ENDPOINT,
            json={"message": "tell me about mosques in Algiers"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "Great Mosque" in data["reply"]

    async def test_success_with_wilaya_filter(self, client: AsyncClient, auth_headers: dict[str, str]):
        mock_data = MagicMock()
        mock_data.summary = "Oran has a beautiful coastline."
        mock_data.pois = []
        mock_data.stays = []
        mock_data.experiences = []
        _inject_mock(client, "travel_agent", _make_mock_agent(mock_data))

        resp = await client.post(
            self.ENDPOINT,
            json={"message": "what to do in Oran?", "wilaya_id": 31},
            headers=auth_headers,
        )
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
        plan = TripPlan(
            destination="Algiers",
            duration_days=3,
            budget_level="mid-range",
            estimated_budget_dzd=25000.0,
            tips=["Visit the Kasbah", "Try couscous"],
            key_attractions=["Grande Mosquée", "Kasbah"],
            itinerary=[
                ItineraryDay(
                    day=1,
                    date="2026-07-16",
                    morning="Visit the Kasbah",
                    afternoon="Lunch in the Casbah",
                    evening="Dinner at El Djenina",
                    meals=[],
                    accommodation="Hotel El Aurassi",
                )
            ],
        )
        _inject_mock(client, "itinerary_agent", _make_mock_agent(plan))

        resp = await client.post(
            self.ENDPOINT,
            json={"destination": "Algiers", "duration_days": 3, "interests": "history, food"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data
        assert data["plan"]["destination"] == "Algiers"
        assert data["plan"]["duration_days"] == 3
        assert len(data["plan"]["itinerary"]) == 1
        assert "Visit the Kasbah" in data["plan"]["itinerary"][0]["morning"]
        assert "El Djenina" in data["plan"]["itinerary"][0]["evening"]


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
        mock_poi = {"id": "1", "name": "Sablettes Beach", "category": "beach", "wilaya_id": 31}
        mock_stay = {"id": "2", "name": "Hotel Oran", "property_type": "hotel", "wilaya_id": 31, "price_per_night_dzd": 5000}
        mock_exp = {"id": "3", "title": "Oran Walking Tour", "category": "tour", "wilaya_id": 31}
        mock_data = MagicMock()
        mock_data.summary = "Found beaches and hotels in Oran."
        mock_data.pois = [mock_poi]
        mock_data.stays = [mock_stay]
        mock_data.experiences = [mock_exp]
        _inject_mock(client, "search_agent", _make_mock_agent(mock_data))

        resp = await client.post(
            self.ENDPOINT,
            json={"query": "beaches and hotels in Oran"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        types = {item["type"] for item in data["results"]}
        assert types == {"poi", "stay", "experience"}

    async def test_empty_results(self, client: AsyncClient, auth_headers: dict[str, str]):
        mock_data = MagicMock()
        mock_data.summary = "Nothing found."
        mock_data.pois = []
        mock_data.stays = []
        mock_data.experiences = []
        _inject_mock(client, "search_agent", _make_mock_agent(mock_data))

        resp = await client.post(
            self.ENDPOINT,
            json={"query": "zzzzzxyznonexistent"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


