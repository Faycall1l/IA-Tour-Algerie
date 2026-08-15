"""Tests for RAG grounding — retrieval + prompt injection.

Covers:
- should_ground() gating (greetings/transport skipped, discovery grounded)
- render_grounding_context() formatting (empty, structure, fun facts)
- RetrievalHit.render() line format
- retrieve_grounding_context() against the real test DB: SQL fallback for
  POIs/stays/experiences, Qdrant path with a fake vector-search service,
  dedup, and graceful empty results
- Renderer integration: grounding context reaches every agent prompt
"""

import uuid

from app.agents.deps import TravelAgentDeps
from app.agents.retrieval import (
    MAX_HITS,
    RetrievalHit,
    render_grounding_context,
    retrieve_grounding_context,
    should_ground,
)
from app.models.experience import Experience
from app.models.poi import POI
from app.models.stay import Stay
from sqlalchemy import select

# ── Pure units ──


class TestShouldGround:
    def test_discovery_queries_are_grounded(self):
        for q in (
            "best beaches in Oran",
            "what to see in Constantine",
            "museums near Timgad",
            "restaurants in Algiers",
        ):
            assert should_ground(q), q

    def test_transport_queries_are_skipped(self):
        for q in (
            "how do I get to Djanet from Algiers?",
            "train from Oran to Tlemcen",
            "comment aller à Tamanrasset",
            "bus from Algiers to Bejaia",
            "what are the flight schedules to Timimoun",
        ):
            assert not should_ground(q), q

    def test_off_topic_greetings_are_skipped(self):
        for q in ("hello", "bonjour", "hi", "merci", "thanks!", "help"):
            assert not should_ground(q), q

    def test_too_short_skipped(self):
        assert not should_ground("plage")


class TestRenderGroundingContext:
    def test_empty_hits_returns_empty(self):
        assert render_grounding_context("any", []) == ""

    def test_renders_markdown_block(self):
        hit = RetrievalHit(
            kind="poi",
            id=uuid.uuid4(),
            name="Palais des Raïs",
            category="historical",
            description="Ottoman-era palace on the Algiers coast.",
            wilaya_id=16,
        )
        block = render_grounding_context("palace algiers", [hit])
        assert "REAL DATA" in block
        assert "Palais des Raïs" in block
        assert "w16" in block
        assert "historical" in block
        assert f"[id:{hit.id}]" in block

    def test_fun_fact_included(self):
        hit = RetrievalHit(
            kind="poi",
            id=uuid.uuid4(),
            name="Timgad",
            category="historical",
            description="Roman colony.",
            wilaya_id=5,
            fun_fact="Founded by Trajan in 100 AD.",
        )
        block = render_grounding_context("timgad", [hit])
        assert "fun fact: Founded by Trajan" in block

    def test_hit_render_uses_kind_labels(self):
        assert (
            RetrievalHit(
                kind="stay",
                id=uuid.uuid4(),
                name="Hotel Ibis",
                category="hotel",
                description="x",
                wilaya_id=31,
            )
            .render()
            .startswith("- [Hebergement w31] Hotel Ibis (hotel):")
        )


# ── DB-backed retrieval ──


async def _seed_catalog(db, user):
    db.add(
        POI(
            name="Plage des Sablettes",
            category="beach",
            wilaya_id=16,
            latitude=36.81,
            longitude=3.16,
            description="Sandy beach on the Algiers bay with family facilities.",
            fun_fact="Named after the golden sand that glows at sunset.",
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


class TestRetrieveGroundingContext:
    async def test_sql_fallback_returns_poi_hits(self, db, test_user):
        await _seed_catalog(db, test_user)
        hits = await retrieve_grounding_context(db, "sablettes", limit=4)
        assert any(h.kind == "poi" and h.name == "Plage des Sablettes" for h in hits)
        poi_hit = next(h for h in hits if h.kind == "poi")
        assert poi_hit.wilaya_id == 16
        assert "fun fact" in poi_hit.fun_fact.lower() or poi_hit.fun_fact is not None

    async def test_sql_fallback_covers_stays(self, db, test_user):
        await _seed_catalog(db, test_user)
        hits = await retrieve_grounding_context(db, "ibis oran", limit=4)
        assert any(h.kind == "stay" and h.name == "Hotel Ibis Oran" for h in hits)

    async def test_sql_fallback_covers_experiences(self, db, test_user):
        await _seed_catalog(db, test_user)
        hits = await retrieve_grounding_context(db, "djurdjura hiking", limit=4)
        assert any(h.kind == "experience" and h.name == "Kabyle Hiking Tour" for h in hits)

    async def test_vector_search_hits_are_fetched(self, db, test_user):
        await _seed_catalog(db, test_user)
        poi = (await db.execute(select(POI).where(POI.name == "Plage des Sablettes"))).scalar_one()

        class FakeVectorSearch:
            def search(self, query, limit=10):
                return [poi.id]

            def search_experiences(self, query, limit=10):
                return []

        hits = await retrieve_grounding_context(db, "sablettes", vector_search=FakeVectorSearch())
        assert any(h.id == poi.id and h.kind == "poi" for h in hits)

    async def test_no_match_returns_empty_not_raise(self, db, test_user):
        await _seed_catalog(db, test_user)
        hits = await retrieve_grounding_context(db, "zzzznonexistentzzzz")
        assert hits == []

    async def test_results_capped_at_limit(self, db, test_user):
        for i in range(6):
            db.add(
                POI(
                    name=f"Plage des Sablettes {i}",
                    category="beach",
                    wilaya_id=16,
                    description="Sandy beach with family facilities.",
                )
            )
        await db.commit()
        hits = await retrieve_grounding_context(db, "sablettes beach", limit=MAX_HITS)
        assert len(hits) <= MAX_HITS


# ── Renderer integration ──


class TestRendererIntegration:
    def _render(self, prompt_name: str, grounding: str) -> str:
        from app.agents.travel_agent import _dynamic_instructions

        class FakeUser:
            full_name = "Tester"
            phone = "+213600000000"
            role = "traveler"

        class FakeCtx:
            def __init__(self, deps):
                self.deps = deps

        deps = TravelAgentDeps(user=FakeUser(), db=None, grounding_context=grounding)
        return _dynamic_instructions(prompt_name)(FakeCtx(deps))

    def test_grounding_reaches_all_five_agents(self):
        block = render_grounding_context(
            "timgad",
            [
                RetrievalHit(
                    kind="poi",
                    id=uuid.uuid4(),
                    name="Timgad",
                    category="historical",
                    description="Roman colony.",
                    wilaya_id=5,
                )
            ],
        )
        for name in (
            "travel_agent.main",
            "travel_agent.itinerary",
            "travel_agent.search",
            "travel_agent.transport",
            "travel_agent.events",
        ):
            prompt = self._render(name, block)
            assert "REAL DATA" in prompt, name
            assert "Timgad" in prompt, name

    def test_empty_grounding_adds_nothing(self):
        prompt = self._render("travel_agent.main", "")
        assert "REAL DATA" not in prompt
        assert "retrieval grounding" not in prompt
