"""Tests for agent memory system — models, service, and tools."""

import uuid
from unittest.mock import MagicMock

import pytest
from app.agents.memory_service import (
    build_message_history,
    delete_session,
    get_next_turn_index,
    get_or_create_session,
    get_user_sessions,
    load_message_history,
    recall,
    remember,
    store_agent_run,
)
from app.agents.memory_tools import recall as recall_tool
from app.agents.memory_tools import remember as remember_tool
from app.models.agent_memory import AgentSession
from sqlalchemy.ext.asyncio import AsyncSession


class TestSession:
    async def _create_test_session(self, db: AsyncSession, user_id: uuid.UUID) -> AgentSession:
        return await get_or_create_session(db, user_id, agent_type="travel_agent")

    @pytest.mark.asyncio
    async def test_create_new_session(self, db: AsyncSession, test_user):
        session = await self._create_test_session(db, test_user.id)
        assert session.id is not None
        assert session.user_id == test_user.id
        assert session.agent_type == "travel_agent"
        assert session.is_active is True

    @pytest.mark.asyncio
    async def test_resume_existing_session(self, db: AsyncSession, test_user):
        s1 = await self._create_test_session(db, test_user.id)
        s2 = await get_or_create_session(
            db, test_user.id, session_id=s1.id, agent_type="travel_agent"
        )
        assert s2.id == s1.id

    @pytest.mark.asyncio
    async def test_resume_wrong_user_rejected(self, db: AsyncSession, test_user):
        from app.models.user import User

        s1 = await self._create_test_session(db, test_user.id)
        other_user = User(id=uuid.uuid4(), phone="+213555999999")
        db.add(other_user)
        await db.commit()
        s2 = await get_or_create_session(
            db, other_user.id, session_id=s1.id, agent_type="travel_agent"
        )
        assert s2.id != s1.id  # New session created for different user


class TestEpisodicMemory:
    @pytest.mark.asyncio
    async def test_store_and_load_turns(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        await store_agent_run(
            db,
            session.id,
            user_message="What to see in Algiers?",
            assistant_reply="Visit the Casbah and Martyrs Memorial.",
            turn_index=1,
            tool_calls=["search_pois"],
        )

        history = await load_message_history(db, session.id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert "Algiers" in history[0]["content"]
        assert history[1]["role"] == "assistant"
        assert "Casbah" in history[1]["content"]

    @pytest.mark.asyncio
    async def test_multiple_turns(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        await store_agent_run(db, session.id, "Turn 1", "Reply 1", turn_index=1)
        await store_agent_run(db, session.id, "Turn 2", "Reply 2", turn_index=3)
        await store_agent_run(db, session.id, "Turn 3", "Reply 3", turn_index=5)

        history = await load_message_history(db, session.id)
        assert len(history) == 6
        assert history[-1]["content"] == "Reply 3"

    @pytest.mark.asyncio
    async def test_turn_index_increment(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        next_idx = await get_next_turn_index(db, session.id)
        assert next_idx == 1  # First turn

        await store_agent_run(db, session.id, "Test", "Reply", turn_index=next_idx)
        next_idx = await get_next_turn_index(db, session.id)
        assert next_idx == 3  # After storing 2 messages (user + assistant)

    @pytest.mark.asyncio
    async def test_empty_history(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        history = await load_message_history(db, session.id)
        assert history == []


class TestSemanticMemory:
    @pytest.mark.asyncio
    async def test_remember_and_recall(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        await remember(db, session.id, key="user_budget", value="mid-range")
        await remember(db, session.id, key="destination", value="Oran")
        await remember(db, session.id, key="travel_month", value="June")

        results = await recall(db, session.id)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_recall_by_key(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        await remember(db, session.id, key="user_budget", value="luxury")
        await remember(db, session.id, key="user_diet", value="vegetarian")

        results = await recall(db, session.id, key="budget")
        assert len(results) == 1
        assert results[0]["value"] == "luxury"

    @pytest.mark.asyncio
    async def test_overwrite_key(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        await remember(db, session.id, key="destination", value="Algiers")
        await remember(db, session.id, key="destination", value="Constantine")

        results = await recall(db, session.id, key="destination")
        assert len(results) == 1
        assert results[0]["value"] == "Constantine"

    @pytest.mark.asyncio
    async def test_recall_empty(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        results = await recall(db, session.id)
        assert results == []


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_list_user_sessions(self, db: AsyncSession, test_user):
        await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        await get_or_create_session(db, test_user.id, agent_type="events_agent")

        sessions = await get_user_sessions(db, test_user.id)
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_delete_session(self, db: AsyncSession, test_user):
        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")

        deleted = await delete_session(db, session.id, test_user.id)
        assert deleted is True

        sessions = await get_user_sessions(db, test_user.id)
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_delete_other_user_session(self, db: AsyncSession, test_user):
        from app.models.user import User

        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        other_user = User(id=uuid.uuid4(), phone="+213555888888")
        db.add(other_user)
        await db.commit()

        deleted = await delete_session(db, session.id, other_user.id)
        assert deleted is False  # Cannot delete another user's session


class TestBuildMessageHistory:
    def test_empty_messages(self):
        result = build_message_history([])
        assert result == ""

    def test_single_turn(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = build_message_history(messages)
        assert "[User]: Hello" in result
        assert "[Assistant]: Hi there" in result

    def test_multiple_turns(self):
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply A"},
            {"role": "user", "content": "Second"},
            {"role": "assistant", "content": "Reply B"},
        ]
        result = build_message_history(messages)
        assert "PREVIOUS CONVERSATION" in result
        assert result.count("[User]:") == 2
        assert result.count("[Assistant]:") == 2


class TestMemoryTools:
    @pytest.mark.asyncio
    async def test_remember_tool_no_session(self):
        ctx = MagicMock()
        ctx.deps.session_id = None
        params = MagicMock()
        params.key = "test"
        params.value = "value"

        result = await remember_tool(ctx, params)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_recall_tool_no_session(self):
        ctx = MagicMock()
        ctx.deps.session_id = None
        params = MagicMock()
        params.key = None

        result = await recall_tool(ctx, params)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_remember_tool_success(self, db: AsyncSession, test_user):
        from app.agents.deps import TravelAgentDeps

        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        deps = TravelAgentDeps(user=test_user, db=db, session_id=session.id)

        ctx = MagicMock()
        ctx.deps = deps
        params = MagicMock()
        params.key = "test_pref"
        params.value = "test_value"

        result = await remember_tool(ctx, params)
        assert result.status == "ok"
        assert "test_pref" in result.message

    @pytest.mark.asyncio
    async def test_recall_tool_success(self, db: AsyncSession, test_user):
        from app.agents.deps import TravelAgentDeps

        session = await get_or_create_session(db, test_user.id, agent_type="travel_agent")
        deps = TravelAgentDeps(user=test_user, db=db, session_id=session.id)

        await remember(db, session.id, key="my_fact", value="my_value")

        ctx = MagicMock()
        ctx.deps = deps
        params = MagicMock()
        params.key = "my_fact"

        result = await recall_tool(ctx, params)
        assert result.total == 1
        assert result.results[0].value == "my_value"
