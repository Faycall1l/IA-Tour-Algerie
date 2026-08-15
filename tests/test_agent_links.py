"""Tests for structured deep links attached to agent replies.

Covers:
- Pure link helpers: relative/absolute url builders, per-tool extraction from
  validated tool outputs (dict, JSON string, and Pydantic model payloads),
  the result-walking collector (dict + object parts, dedupe, cap, mock-tolerance),
  and the plain-text footer renderer
- Fallback path: attempt_fallback_with_links emits the same links the LLM path
  would (against the real test DB)
- Endpoint integration: a no-agent degraded reply carries links[] + the footer
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.agents.links import (
    AgentLink,
    collect_links_from_result,
    link_url,
    links_from_tool_output,
    render_links_section,
    transport_link,
)
from app.agents.tools import POISearchOutput, POISearchResult
from httpx import AsyncClient

_POI_RESULTS = {
    "results": [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Plage des Sablettes",
            "category": "beach",
            "wilaya_id": 16,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Palais des Raïs",
            "category": "cultural",
            "wilaya_id": 16,
        },
    ],
    "total": 2,
}


# ── Url builders ──


class TestUrlBuilders:
    def test_link_url_relative(self):
        assert link_url("poi", "abc") == "/pois/abc"
        assert link_url("stay", "xyz") == "/stays/xyz"
        assert link_url("experience", 42) == "/experiences/42"
        assert link_url("event", "e1") == "/events/e1"
        assert link_url("artisan", "a1") == "/artisans/a1"
        assert link_url("wilaya", 16) == "/wilayas/16"
        assert link_url("transport", 1) == ""
        assert link_url("unknown", 1) == ""

    def test_link_url_absolute(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "app_url", "https://athar.app/")
        assert link_url("poi", "abc") == "https://athar.app/pois/abc"
        assert (
            transport_link(16, 31)
            == "https://athar.app/transport/plan?from_wilaya=16&to_wilaya=31"
        )

    def test_transport_link_relative(self):
        assert transport_link(16, 31) == "/transport/plan?from_wilaya=16&to_wilaya=31"


# ── Tool-output extraction ──


class TestLinksFromToolOutput:
    def test_poi_results(self):
        links = links_from_tool_output("search_pois", json.dumps(_POI_RESULTS))
        assert len(links) == 2
        assert links[0].type == "poi"
        assert links[0].id == "11111111-1111-1111-1111-111111111111"
        assert links[0].name == "Plage des Sablettes"
        assert links[0].url == "/pois/11111111-1111-1111-1111-111111111111"
        assert links[0].wilaya_id == 16

    def test_stay_results(self):
        links = links_from_tool_output(
            "search_stays",
            {"results": [{"id": "s1", "name": "Hotel Ibis Oran", "wilaya_id": 31}]},
        )
        assert len(links) == 1
        assert links[0].type == "stay"
        assert links[0].url == "/stays/s1"

    def test_experience_results_uses_title(self):
        links = links_from_tool_output(
            "search_experiences",
            {"results": [{"id": "x1", "title": "Kabyle Hiking Tour", "wilaya_id": 15}]},
        )
        assert len(links) == 1
        assert links[0].type == "experience"
        assert links[0].name == "Kabyle Hiking Tour"
        assert links[0].url == "/experiences/x1"

    def test_artisan_results(self):
        links = links_from_tool_output(
            "search_artisans",
            {"results": [{"id": "a1", "name": "Atelier de Poterie", "wilaya_id": 16}]},
        )
        assert len(links) == 1
        assert links[0].type == "artisan"
        assert links[0].url == "/artisans/a1"

    def test_event_results_uses_title(self):
        links = links_from_tool_output(
            "find_events",
            {"results": [{"id": "e1", "title": "Yennayer Festival", "wilaya_id": 15}]},
        )
        assert len(links) == 1
        assert links[0].type == "event"
        assert links[0].url == "/events/e1"

    def test_wilaya_guide_result(self):
        out = {
            "wilaya_id": 16,
            "wilaya_name": "Algiers",
            "featured_pois": [_POI_RESULTS["results"][0]],
            "categories": [
                {"category": "beach", "count": 1, "pois": [_POI_RESULTS["results"][0]]}
            ],
            "top_stays": [{"id": "s1", "name": "Hotel Ibis", "wilaya_id": 16}],
            "top_experiences": [{"id": "x1", "title": "Old City Walk", "wilaya_id": 16}],
        }
        links = links_from_tool_output("get_wilaya_guide", out)
        types = {lnk.type for lnk in links}
        assert types == {"wilaya", "poi", "stay", "experience"}
        wilaya = next(lnk for lnk in links if lnk.type == "wilaya")
        assert wilaya.id == "16"
        assert wilaya.url == "/wilayas/16"

    def test_transport_result(self):
        links = links_from_tool_output(
            "get_transport_route",
            {
                "origin_wilaya_id": 16,
                "dest_wilaya_id": 31,
                "origin_wilaya": "Algiers",
                "dest_wilaya": "Oran",
            },
        )
        assert len(links) == 1
        assert links[0].type == "transport"
        assert links[0].url == "/transport/plan?from_wilaya=16&to_wilaya=31"
        assert links[0].name == "Transport Algiers → Oran"
        assert links[0].wilaya_id == 16

    def test_transport_result_without_ids(self):
        assert links_from_tool_output("get_transport_route", {"options": []}) == []

    def test_unknown_tool(self):
        assert links_from_tool_output("get_weather", _POI_RESULTS) == []

    def test_malformed_payload(self):
        assert links_from_tool_output("search_pois", "not-json") == []
        assert links_from_tool_output("search_pois", None) == []

    def test_pydantic_model_payload(self):
        model = POISearchOutput(
            results=[POISearchResult(id="m1", name="Modèle POI", category="museum", wilaya_id=25)],
            total=1,
        )
        links = links_from_tool_output("search_pois", model)
        assert len(links) == 1
        assert links[0].id == "m1"
        assert links[0].url == "/pois/m1"


# ── Result collector ──


def _part(tool_name: str, content: str | dict) -> SimpleNamespace:
    return SimpleNamespace(part_kind="tool-return", tool_name=tool_name, content=content)


def _message(*parts) -> SimpleNamespace:
    return SimpleNamespace(parts=list(parts))


class TestCollectLinksFromResult:
    def test_collects_and_dedupes(self):
        content = json.dumps(_POI_RESULTS)
        result = MagicMock()
        result.all_messages = MagicMock(
            return_value=[
                _message(_part("search_pois", content)),
                _message(_part("search_pois", content)),
                _message(_part("find_events", json.dumps(
                    {"results": [{"id": "e1", "title": "Festival", "wilaya_id": 15}]}
                ))),
            ]
        )
        links = collect_links_from_result(result)
        assert len(links) == 3
        assert {(lnk.type, lnk.id) for lnk in links} == {
            ("poi", "11111111-1111-1111-1111-111111111111"),
            ("poi", "22222222-2222-2222-2222-222222222222"),
            ("event", "e1"),
        }

    def test_dict_and_object_parts(self):
        result = MagicMock()
        result.all_messages = MagicMock(
            return_value=[
                SimpleNamespace(
                    parts=[
                        dict(
                            part_kind="tool-return",
                            tool_name="search_pois",
                            content=_POI_RESULTS,
                        )
                    ]
                ),
                _message(
                    _part(
                        "search_stays",
                        {"results": [{"id": "s1", "name": "Ibis", "wilaya_id": 31}]},
                    )
                ),
            ]
        )
        links = collect_links_from_result(result)
        assert len(links) == 3

    def test_cap_limits_links(self):
        result = MagicMock()
        result.all_messages = MagicMock(
            return_value=[_message(_part("search_pois", json.dumps(_POI_RESULTS)))]
        )
        links = collect_links_from_result(result, max_links=1)
        assert len(links) == 1

    def test_tolerates_mocked_result_without_messages(self):
        result = MagicMock()
        links = collect_links_from_result(result)
        assert links == []


# ── Footer renderer ──


class TestRenderLinksSection:
    def test_empty(self):
        assert render_links_section([]) == ""

    def test_renders_footer(self):
        links = [
            AgentLink(type="poi", id="abc", name="Sablettes", url="/pois/abc"),
            AgentLink(type="stay", id="s1", name="Ibis", url="/stays/s1"),
        ]
        text = render_links_section(links)
        assert text.startswith("\n\nQuick links:")
        assert "Sablettes: /pois/abc" in text
        assert "Ibis: /stays/s1" in text

    def test_cap(self):
        links = [
            AgentLink(type="poi", id=str(i), name=f"P{i}", url=f"/pois/{i}") for i in range(8)
        ]
        text = render_links_section(links, max_links=2)
        assert text.count(": /pois/") == 2


# ── Fallback path (real test DB) ──


async def _seed_beach(db) -> str:
    """Seed a uniquely-named beach POI in Algiers; returns its id."""
    from app.models.poi import POI

    poi = POI(
        name="Plage des Sablettes LinkTest",
        category="beach",
        wilaya_id=16,
        latitude=36.81,
        longitude=3.16,
        description="Sandy beach on the Algiers bay with family facilities.",
        price_level="Free",
        suggested_duration_min=60,
    )
    db.add(poi)
    await db.commit()
    await db.refresh(poi)
    return str(poi.id)


class TestFallbackWithLinks:
    pytestmark = pytest.mark.asyncio

    async def test_poi_search_returns_links(self, db, test_user):
        from app.agents.deps import TravelAgentDeps
        from app.agents.fallback import attempt_fallback_with_links

        poi_id = await _seed_beach(db)
        text, links = await attempt_fallback_with_links(
            "travel_agent", "beaches in Algiers", TravelAgentDeps(user=test_user, db=db)
        )
        assert text is not None
        assert "Sablettes" in text
        assert any(
            lnk.type == "poi" and lnk.id == poi_id and lnk.url == f"/pois/{poi_id}"
            for lnk in links
        )

    async def test_transport_route_returns_link(self, db, test_user, monkeypatch):
        from app.agents import fallback as fb
        from app.agents.deps import TravelAgentDeps
        from app.agents.fallback import attempt_fallback_with_links
        from app.agents.tools import TransportModeOption, TransportRouteResult

        async def fake_route(_ctx, _params):
            return TransportRouteResult(
                origin_wilaya="Algiers",
                dest_wilaya="Oran",
                origin_wilaya_id=16,
                dest_wilaya_id=31,
                options=[TransportModeOption(mode="train", cost_dzd=2500.0, duration_min=180)],
                best_recommendation="Cheapest: train at 2500 DZD",
            )

        monkeypatch.setattr(fb, "get_transport_route", fake_route)
        text, links = await attempt_fallback_with_links(
            "transport_agent",
            "how to get from Algiers to Oran",
            TravelAgentDeps(user=test_user, db=db),
        )
        assert text is not None
        assert any(
            lnk.type == "transport"
            and lnk.url == "/transport/plan?from_wilaya=16&to_wilaya=31"
            and lnk.name == "Transport Algiers → Oran"
            for lnk in links
        )


# ── Endpoint integration ──


def _clear_travel_agent(app):
    saved = getattr(app.state, "travel_agent", None)
    if hasattr(app.state, "travel_agent"):
        delattr(app.state, "travel_agent")

    def restore():
        if saved is None:
            if hasattr(app.state, "travel_agent"):
                delattr(app.state, "travel_agent")
        else:
            app.state.travel_agent = saved

    return restore


class TestEndpointLinks:
    pytestmark = pytest.mark.asyncio
    ENDPOINT = "/api/v1/agent/chat"

    async def test_no_agent_degrades_with_links(
        self, client: AsyncClient, auth_headers, db, test_user
    ):
        from app.main import app

        restore = _clear_travel_agent(app)
        try:
            await _seed_beach(db)
            resp = await client.post(
                self.ENDPOINT,
                json={"message": "beaches in Algiers"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["degraded"] is True
            assert isinstance(data["links"], list)
            assert len(data["links"]) >= 1
            assert data["links"][0]["type"] == "poi"
            assert data["links"][0]["url"].startswith("/pois/")
            assert "Quick links:" in data["reply"]
            assert "/pois/" in data["reply"]
        finally:
            restore()
