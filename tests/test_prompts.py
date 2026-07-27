"""Tests for the agent prompt management system — versioning, registry, context."""

import pytest

from app.agents.prompts import (
    AgentContext,
    Prompt,
    PromptRegistry,
    build_prompt,
    registry,
)


class TestPrompt:
    def test_render_basic(self):
        p = Prompt(name="test", version="1.0", template="Hello {name}, welcome to {city}")
        result = p.render(name="Faycal", city="Oran")
        assert result == "Hello Faycal, welcome to Oran"

    def test_render_missing_var_kept(self):
        p = Prompt(name="test", version="1.0", template="Hello {name}, visit {city}")
        result = p.render(name="Faycal")
        assert "Faycal" in result
        assert "{city}" in result

    def test_variables_detected(self):
        p = Prompt(name="test", version="1.0", template="{a} and {b} and {a} again")
        assert set(p.variables) == {"a", "b"}

    def test_frozen(self):
        p = Prompt(name="t", version="1", template="x")
        with pytest.raises(AttributeError):
            p.name = "changed"


class TestPromptRegistry:
    def test_register_and_get(self):
        reg = PromptRegistry()
        reg.register(Prompt(name="agent.main", version="1.0", template="Hello"))
        p = reg.get("agent.main")
        assert p.version == "1.0"

    def test_get_latest(self):
        reg = PromptRegistry()
        reg.register(Prompt(name="a", version="1.0", template="v1"))
        reg.register(Prompt(name="a", version="2.0", template="v2"))
        assert reg.get("a").version == "2.0"

    def test_get_specific_version(self):
        reg = PromptRegistry()
        reg.register(Prompt(name="a", version="1.0", template="v1"))
        reg.register(Prompt(name="a", version="2.0", template="v2"))
        assert reg.get("a", "1.0").version == "1.0"

    def test_duplicate_version_raises(self):
        reg = PromptRegistry()
        reg.register(Prompt(name="a", version="1.0", template="x"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(Prompt(name="a", version="1.0", template="y"))

    def test_missing_prompt_raises(self):
        reg = PromptRegistry()
        with pytest.raises(KeyError, match="not found"):
            reg.get("nonexistent")

    def test_list_prompts(self):
        reg = PromptRegistry()
        reg.register(Prompt(name="a", version="1.0", template="x", description="Test A"))
        reg.register(Prompt(name="a", version="2.0", template="y", description="Test A v2"))
        reg.register(Prompt(name="b", version="1.0", template="z", description="Test B"))
        items = reg.list_prompts()
        assert len(items) == 2
        a_item = next(i for i in items if i["name"] == "a")
        assert a_item["versions"] == ["1.0", "2.0"]
        assert a_item["latest"] == "2.0"

    def test_len(self):
        reg = PromptRegistry()
        assert len(reg) == 0
        reg.register(Prompt(name="a", version="1.0", template="x"))
        assert len(reg) == 1


class TestGlobalRegistry:
    def test_has_travel_prompts(self):
        assert len(registry) >= 3

    def test_travel_agent_main_prompt(self):
        p = registry.get("travel_agent.main")
        assert "ATHAR" in p.template
        assert p.version == "1.0.0"

    def test_itinerary_prompt(self):
        p = registry.get("travel_agent.itinerary")
        assert "itinerary" in p.template.lower() or "Itinerary" in p.template

    def test_search_prompt(self):
        p = registry.get("travel_agent.search")
        assert "search" in p.template.lower()

    def test_transport_prompt(self):
        p = registry.get("travel_agent.transport")
        assert "transport" in p.template.lower()
        assert "SNTF" in p.template

    def test_events_prompt(self):
        p = registry.get("travel_agent.events")
        assert "events" in p.template.lower() or "festivals" in p.template.lower()

    def test_all_agents_have_context_placeholder(self):
        for item in registry.list_prompts():
            p = registry.get(item["name"])
            assert "{context}" in p.template, f"{item['name']} missing {{context}}"


class TestAgentContext:
    def test_empty_context(self):
        ctx = AgentContext()
        rendered = ctx.render()
        assert rendered == ""

    def test_with_user(self):
        class FakeUser:
            full_name = "Faycal"
            role = "traveler"
        ctx = AgentContext.from_user(FakeUser())
        assert ctx.user_name == "Faycal"
        assert ctx.today  # Should have today's date

    def test_render_with_fields(self):
        ctx = AgentContext(today="2026-07-26", user_name="Faycal", wilaya_name="Oran")
        rendered = ctx.render()
        assert "2026-07-26" in rendered
        assert "Faycal" in rendered
        assert "Oran" in rendered

    def test_custom_context(self):
        ctx = AgentContext(custom={"weather": "Sunny 32C"})
        rendered = ctx.render()
        assert "SUNNY" in rendered.upper()


class TestBuildPrompt:
    def test_build_with_version(self):
        p = build_prompt("travel_agent.main", version="1.0.0")
        assert "ATHAR" in p

    def test_build_injects_context(self):
        class FakeUser:
            full_name = "Test"
            role = "traveler"
        p = build_prompt("travel_agent.main", user=FakeUser())
        assert "Test" in p
        assert "TODAY'S DATE" in p

    def test_build_with_extra_context(self):
        p = build_prompt(
            "travel_agent.main",
            extra_context={"weather": "Sunny"},
        )
        assert "WEATHER" in p or "weather" in p.lower()
