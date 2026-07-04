class TestAgentLLM:
    def test_get_llm_disabled_by_default(self):
        from app.services.agent.llm import get_llm

        llm = get_llm()
        assert llm is None


class TestAgentMiddleware:
    def test_logging_middleware_imports(self):
        from app.services.agent.middleware import (
            AtharLoggingMiddleware,
            MetricsMiddleware,
        )

        assert AtharLoggingMiddleware is not None
        assert MetricsMiddleware is not None

    def test_metrics_middleware_imports(self):
        from app.services.agent.middleware import _AGENT_CALLS

        _AGENT_CALLS.labels(agent="test").inc()


class TestAgentRegistry:
    async def test_search_pois_no_session(self):
        from app.services.agent.registry import search_pois

        result = await search_pois.ainvoke({"query": "mosque"})
        assert result == []

    async def test_get_price_estimate_no_session(self):
        from app.services.agent.registry import get_price_estimate

        result = await get_price_estimate.ainvoke(
            {
                "item_type": "poi",
                "item_id": "00000000-0000-0000-0000-000000000000",
            }
        )
        assert result["count"] == 0

    async def test_get_review_summary_no_session(self):
        from app.services.agent.registry import get_review_summary

        result = await get_review_summary.ainvoke(
            {
                "item_type": "poi",
                "item_id": "00000000-0000-0000-0000-000000000000",
            }
        )
        assert result["total_reviews"] == 0

    async def test_get_experience_no_session(self):
        from app.services.agent.registry import get_experience

        result = await get_experience.ainvoke(
            {
                "experience_id": "00000000-0000-0000-0000-000000000000",
            }
        )
        assert result is None

    async def test_get_stay_no_session(self):
        from app.services.agent.registry import get_stay

        result = await get_stay.ainvoke(
            {
                "stay_id": "00000000-0000-0000-0000-000000000000",
            }
        )
        assert result is None

    async def test_compute_travel_time(self):
        from app.services.agent.registry import compute_travel_time

        result = await compute_travel_time.ainvoke(
            {
                "origin_lat": 36.737,
                "origin_lng": 3.068,
                "dest_lat": 36.753,
                "dest_lng": 3.058,
            }
        )
        assert "distance_km" in result
        assert "duration_minutes" in result
        assert result["mode"] == "walking"

    async def test_find_nearby_no_session(self):
        from app.services.agent.registry import find_nearby

        result = await find_nearby.ainvoke(
            {
                "lat": 36.737,
                "lng": 3.068,
            }
        )
        assert result == []


class TestAgentSession:
    def test_session_create(self):
        from app.services.agent.session import UserSession

        s = UserSession(user_id="test-123")
        assert s.user_id == "test-123"
        assert s.locale == "en"

    def test_session_to_from_dict(self):
        from app.services.agent.session import UserSession

        s = UserSession(user_id="test-123")
        s.locale = "fr"
        s.intent = {"budget_tier": "economy"}

        data = s.to_dict()
        restored = UserSession.from_dict(data)
        assert restored.user_id == "test-123"
        assert restored.locale == "fr"
        assert restored.intent == {"budget_tier": "economy"}

    async def test_session_store(self):
        from app.services.agent.session import SessionStore

        store = SessionStore()
        s = await store.get("user-1")
        assert s.user_id == "user-1"

        s.locale = "ar"
        await store.save(s)

        s2 = await store.get("user-1")
        assert s2.locale == "ar"


class TestAgentSubagents:
    def test_trip_optimizer_agent_disabled_when_no_llm(self):
        from app.services.agent.agents.trip_optimizer import get_trip_optimizer_agent

        agent = get_trip_optimizer_agent()
        assert agent is None

    def test_trip_brief_agent_disabled_when_no_llm(self):
        from app.services.agent.agents.trip_brief import get_trip_brief_agent

        agent = get_trip_brief_agent()
        assert agent is None

    def test_coordinator_disabled_when_no_llm(self):
        from app.services.agent.agents.coordinator import get_coordinator

        coordinator = get_coordinator()
        assert coordinator is None
