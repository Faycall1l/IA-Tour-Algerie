class TestAgentLLM:
    def test_get_llm_disabled_by_default(self):
        from unittest.mock import patch
        from app.services.agent.llm import get_llm

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
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

    async def test_logging_middleware_hooks(self):
        from app.services.agent.middleware import AtharLoggingMiddleware

        class _S:
            messages = []
            structured_response = None

        class _R:
            config = {"agent_name": "test"}

        mw = AtharLoggingMiddleware()
        s = _S()
        r = _R()

        await mw.before_model(s, r)
        assert hasattr(s, "_athar_start")
        assert isinstance(s._athar_start, float)

        await mw.after_model(s, r)
        await mw.after_agent(s, r)

    async def test_metrics_middleware_hooks(self):
        from app.services.agent.middleware import MetricsMiddleware

        class _S:
            structured_response = None

        class _R:
            config = {"agent_name": "test"}

        class _TC:
            name = "test_tool"

        class _Res:
            duration = 0.42

        mw = MetricsMiddleware()
        s = _S()
        r = _R()

        await mw.after_tool(s, r, _TC(), _Res())
        await mw.after_agent(s, r)

    async def test_context_injection_skips_english(self):
        from app.services.agent.middleware import ContextInjectionMiddleware
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext(locale="en"))

        msg_cls = type("Msg", (), {"content": "System prompt"})

        class _S:
            messages = [msg_cls()]
            structured_response = None

        mw = ContextInjectionMiddleware()
        s = _S()
        await mw.before_model(s, None)
        assert s.messages[0].content == "System prompt"

        set_tool_context(ToolContext())

    async def test_context_injection_injects_french_locale(self):
        from app.services.agent.middleware import ContextInjectionMiddleware
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext(locale="fr"))
        try:

            class _S:
                pass

            mw = ContextInjectionMiddleware()
            s = _S()
            s.messages = [type("Msg", (), {"content": "System prompt"})()]
            await mw.before_model(s, None)
            assert s.messages[0].content == "System prompt\n\nUser locale: fr"
        finally:
            set_tool_context(ToolContext())

    async def test_context_injection_skips_empty_messages(self):
        from app.services.agent.middleware import ContextInjectionMiddleware
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext(locale="ar"))
        try:

            class _S:
                messages = []

            mw = ContextInjectionMiddleware()
            s = _S()
            await mw.before_model(s, None)
        finally:
            set_tool_context(ToolContext())


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


class TestToolContext:
    def test_tool_context_default(self):
        from app.services.agent.session import ToolContext

        ctx = ToolContext()
        assert ctx.db_session is None
        assert ctx.user_id == ""
        assert ctx.trip_id == ""
        assert ctx.locale == "en"

    def test_tool_context_set_values(self):
        from app.services.agent.session import ToolContext

        ctx = ToolContext(user_id="u1", trip_id="t1", locale="fr")
        assert ctx.user_id == "u1"
        assert ctx.trip_id == "t1"
        assert ctx.locale == "fr"

    def test_get_set_tool_context(self):
        from app.services.agent.session import (
            ToolContext,
            get_tool_context,
            set_tool_context,
        )

        assert get_tool_context().db_session is None
        ctx = ToolContext(user_id="u2", locale="ar")
        set_tool_context(ctx)
        assert get_tool_context().user_id == "u2"
        assert get_tool_context().locale == "ar"
        set_tool_context(ToolContext())

    def test_agent_context_extends_tool_context(self):
        from app.services.agent.session import AgentContext

        ctx = AgentContext(user_id="u3", thread_id="th-1")
        assert ctx.user_id == "u3"
        assert ctx.thread_id == "th-1"
        assert ctx.db_session is None

    async def test_tools_with_context_no_db(self):
        from app.services.agent.registry import search_pois
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext(user_id="test"))
        result = await search_pois.ainvoke({"query": "mosque"})
        assert result == []
        set_tool_context(ToolContext())

    def test_tool_context_dataclass_defaults(self):
        import dataclasses  # noqa: E402

        from app.services.agent.session import ToolContext

        field_names = {f.name for f in dataclasses.fields(ToolContext)}
        assert "db_session" in field_names
        assert "user_id" in field_names
        assert "trip_id" in field_names
        assert "locale" in field_names


class TestAgentSchemas:
    def test_trip_optimizer_output_defaults(self):
        from app.services.agent.schemas import TripOptimizerOutput

        out = TripOptimizerOutput()
        assert out.days == []
        assert out.budget_spent == 0
        assert out.budget_remaining == 0
        assert out.gaps == []
        assert out.optimization_score == 0.0
        assert out.suggestions == []

    def test_trip_optimizer_output_scores(self):
        from app.services.agent.schemas import TripOptimizerOutput

        out = TripOptimizerOutput(optimization_score=85, budget_spent=12000)
        assert out.optimization_score == 85
        assert out.budget_spent == 12000

    def test_wilaya_brief_output_defaults(self):
        from app.services.agent.schemas import WilayaBriefOutput

        brief = WilayaBriefOutput()
        assert brief.wilaya == ""
        assert brief.top_pois == []
        assert brief.experiences == []
        assert brief.best_months == []
        assert brief.review_highlights == []
        assert brief.practical_tips == []

    def test_coordinator_output_defaults(self):
        from app.services.agent.schemas import CoordinatorOutput

        out = CoordinatorOutput()
        assert out.action == ""
        assert out.result is None
        assert out.rationale == ""

    def test_day_plan_validation(self):
        from app.services.agent.schemas import DayPlan

        dp = DayPlan(day_number=1, items=["a", "b"], description="Day one")
        assert dp.day_number == 1
        assert dp.items == ["a", "b"]
        assert dp.description == "Day one"

    def test_top_poi_fields(self):
        from app.services.agent.schemas import TopPOI

        poi = TopPOI(id="abc", name="Test", category="historical", review_score=4.5)
        assert poi.id == "abc"
        assert poi.category == "historical"
        assert poi.review_score == 4.5


class TestAgentLLMFallback:
    def test_get_fallback_disabled_by_default(self):
        from unittest.mock import patch
        from app.services.agent.llm import get_llm

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
            fallback = get_llm(fallback=True)
            assert fallback is None

    def test_reset_llm(self):
        from unittest.mock import patch
        from app.services.agent.llm import get_llm, reset_llm

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
            reset_llm()
            assert get_llm() is None
            assert get_llm(fallback=True) is None


class TestToolEdgeCases:
    async def test_search_pois_with_context_returns_empty_no_db(self):
        from app.services.agent.registry import search_pois
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext(user_id="u", trip_id="t"))
        result = await search_pois.ainvoke({"query": "mosque"})
        assert result == []
        set_tool_context(ToolContext())

    async def test_get_price_estimate_bad_uuid(self):
        from app.services.agent.registry import get_price_estimate

        result = await get_price_estimate.ainvoke({"item_type": "poi", "item_id": "not-a-uuid"})
        assert result["count"] == 0

    async def test_compute_travel_time_zero_distance(self):
        from app.services.agent.registry import compute_travel_time

        result = await compute_travel_time.ainvoke(
            {"origin_lat": 36.0, "origin_lng": 3.0, "dest_lat": 36.0, "dest_lng": 3.0}
        )
        assert result["distance_km"] == 0
        assert result["duration_minutes"] == 0

    async def test_compute_travel_time_driving_mode(self):
        from app.services.agent.registry import compute_travel_time

        result = await compute_travel_time.ainvoke(
            {
                "origin_lat": 36.737,
                "origin_lng": 3.068,
                "dest_lat": 36.753,
                "dest_lng": 3.058,
                "mode": "driving",
            }
        )
        assert result["mode"] == "driving"
        assert result["distance_km"] > 0

    async def test_find_nearby_empty_types(self):
        from app.services.agent.registry import find_nearby
        from app.services.agent.session import ToolContext, set_tool_context

        set_tool_context(ToolContext())
        result = await find_nearby.ainvoke({"lat": 36.0, "lng": 3.0, "types": ""})
        assert result == []
        set_tool_context(ToolContext())

    async def test_tool_context_is_task_isolated(self):
        from app.services.agent.session import (
            ToolContext,
            get_tool_context,
            set_tool_context,
        )

        set_tool_context(ToolContext(user_id="main-task"))

        async def subtask():
            return get_tool_context().user_id

        sub_user = await subtask()
        main_user = get_tool_context().user_id
        assert main_user == "main-task"
        assert sub_user == "main-task"
        set_tool_context(ToolContext())

    async def test_agent_context_with_future(self):
        from app.services.agent.session import AgentContext

        ctx = AgentContext(user_id="future", thread_id="th-99", locale="ar")
        assert ctx.user_id == "future"
        assert ctx.thread_id == "th-99"
        assert ctx.locale == "ar"


class TestCheckpointMiddleware:
    def test_checkpoint_init_default(self):
        from app.services.agent.middleware import CheckpointMiddleware

        mw = CheckpointMiddleware()
        assert mw._store == {}

    def test_checkpoint_init_with_store(self):
        from app.services.agent.middleware import CheckpointMiddleware

        store: dict = {}
        mw = CheckpointMiddleware(store=store)
        assert mw._store is store

    async def test_checkpoint_save_and_restore(self):
        from app.services.agent.middleware import CheckpointMiddleware
        from app.services.agent.session import AgentContext, set_tool_context

        store: dict = {}
        mw = CheckpointMiddleware(store=store)

        set_tool_context(AgentContext(thread_id="th-1"))

        class _S:
            def __init__(self):
                self.messages = ["msg1", "msg2"]
                self.structured_response = None

        s = _S()
        await mw.before_model(s, None)
        assert s.messages == ["msg1", "msg2"]

        await mw.after_agent(s, None)
        assert "th-1" in store
        assert store["th-1"] == ["msg1", "msg2"]

        s2 = _S()
        s2.messages = ["replacement"]
        await mw.before_model(s2, None)
        assert s2.messages == ["msg1", "msg2"]

        set_tool_context(AgentContext())

    async def test_checkpoint_no_thread_id(self):
        from app.services.agent.middleware import CheckpointMiddleware

        mw = CheckpointMiddleware()

        class _S:
            def __init__(self):
                self.messages = ["msg"]
                self.structured_response = None

        s = _S()
        await mw.after_agent(s, None)
        assert mw._store == {}


class TestAgentSubagents:
    def test_trip_optimizer_agent_disabled_when_no_llm(self):
        from unittest.mock import patch
        from app.services.agent.agents.trip_optimizer import get_trip_optimizer_agent

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
            agent = get_trip_optimizer_agent()
            assert agent is None

    def test_trip_brief_agent_disabled_when_no_llm(self):
        from unittest.mock import patch
        from app.services.agent.agents.trip_brief import get_trip_brief_agent

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
            agent = get_trip_brief_agent()
            assert agent is None

    def test_coordinator_disabled_when_no_llm(self):
        from unittest.mock import patch
        from app.services.agent.agents.coordinator import get_coordinator

        with patch("app.services.agent.llm.settings") as mock_settings:
            mock_settings.agent.vllm.api_key = ""
            mock_settings.agent.vllm.base_url = ""
            coordinator = get_coordinator()
            assert coordinator is None
