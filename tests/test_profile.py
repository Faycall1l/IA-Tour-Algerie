"""Tests for the persistent traveler profile — mining, merge, render, API.

Covers:
- Deterministic mining: budget, interests, travel style, home wilaya (DB-backed)
- Conservative mining: greetings / non-signals produce an empty MinedProfile
- merge(): union of interests, overwrite-on-signal, no-op on absent signals
- render(): empty → "", populated → compact PROFILE block
- load_or_create_profile() against the real test DB
- API: GET/PUT /users/me/traveler-profile with auth
"""

import uuid

from app.agents.deps import TravelAgentDeps
from app.agents.profile import (
    load_or_create_profile,
    merge,
    mine_profile,
    render,
)
from app.models.user_profile import UserProfile


class TestMining:
    async def test_budget_detection(self, db):
        assert (await mine_profile(db, "plan a budget trip to Oran")).budget_level == "budget"
        assert (
            await mine_profile(db, "want something luxury with 5 etoiles hotels")
        ).budget_level == "luxury"  # noqa: E501
        assert (await mine_profile(db, "mid-range hotels please")).budget_level == "mid-range"
        assert (await mine_profile(db, "cheap places")).budget_level == "budget"
        assert (await mine_profile(db, "pas cher")).budget_level == "budget"

    async def test_interests_detection(self, db):
        mined = await mine_profile(db, "I love beaches and good food")
        assert "beach" in mined.interests
        assert "food" in mined.interests

    async def test_interests_capped(self, db):
        mined = await mine_profile(
            db,
            "beach museum mountain food culture adventure relax family hiking",
        )
        assert len(mined.interests) <= 6

    async def test_travel_style_detection(self, db):
        assert (await mine_profile(db, "solo backpacking trip")).travel_style == "solo"
        assert (await mine_profile(db, "family holidays with kids")).travel_style == "family"
        assert (await mine_profile(db, "culture and museums")).travel_style == "cultural"
        assert (await mine_profile(db, "trekking in the Hoggar")).travel_style == "adventure"

    async def test_home_wilaya_detection(self, db):
        mined = await mine_profile(db, "I'm in Oran for 2 days")
        assert mined.home_wilaya_id == 31
        mined = await mine_profile(db, "what to see in Constantine")
        assert mined.home_wilaya_id == 25

    async def test_english_wilaya_names(self, db):
        assert (await mine_profile(db, "I am based in Algiers")).home_wilaya_id == 16
        assert (await mine_profile(db, "from Bejaia")).home_wilaya_id == 6

    async def test_conservative_on_greetings(self, db):
        mined = await mine_profile(db, "hello, how are you?")
        assert mined.is_empty


class TestMerge:
    def _profile(self, **kw) -> UserProfile:
        return UserProfile(user_id=uuid.uuid4(), **kw)

    def test_merges_interests_as_union(self):
        profile = self._profile(interests=["history"])
        from app.agents.profile import MinedProfile

        changed = merge(profile, MinedProfile(interests=["beach", "history"]))
        assert changed == ["interests"]
        assert set(profile.interests) == {"history", "beach"}

    def test_no_op_when_nothing_new(self):
        from app.agents.profile import MinedProfile

        profile = self._profile(budget_level="mid-range", interests=["beach"])
        assert merge(profile, MinedProfile()) == []
        assert merge(profile, MinedProfile(budget_level="mid-range")) == []

    def test_overwrites_on_new_signal(self):
        from app.agents.profile import MinedProfile

        profile = self._profile(budget_level="budget")
        changed = merge(profile, MinedProfile(budget_level="luxury"))
        assert changed == ["budget_level"]
        assert profile.budget_level == "luxury"

    def test_absent_signals_preserved(self):
        from app.agents.profile import MinedProfile

        profile = self._profile(budget_level="budget", travel_style="solo")
        assert merge(profile, MinedProfile(home_wilaya_id=31)) == ["home_wilaya_id"]
        assert profile.budget_level == "budget"
        assert profile.travel_style == "solo"
        assert profile.home_wilaya_id == 31


class TestRender:
    def test_empty_profile_renders_empty(self):
        assert render(UserProfile(user_id=uuid.uuid4())) == ""

    def test_populated_profile_renders_block(self):
        block = render(
            UserProfile(
                user_id=uuid.uuid4(),
                budget_level="mid-range",
                interests=["history", "food"],
                home_wilaya_id=31,
                travel_style="cultural",
            ),
            wilaya_name="Oran",
        )
        assert "TRAVELER PROFILE" in block
        assert "Budget: mid-range" in block
        assert "Interests: history, food" in block
        assert "Travel style: cultural" in block
        assert "Home wilaya: Oran (w31)" in block

    def test_render_without_wilaya_name_uses_id(self):
        block = render(
            UserProfile(user_id=uuid.uuid4(), home_wilaya_id=16),
        )
        assert "Home wilaya: 16 (w16)" in block


class TestLoadOrCreate:
    async def test_creates_then_returns_same(self, db, test_user):
        first = await load_or_create_profile(db, test_user.id)
        assert first.user_id == test_user.id
        await db.commit()
        second = await load_or_create_profile(db, test_user.id)
        assert second is first


class TestRendererIntegration:
    def _render(self, prompt_name: str, profile_context: str) -> str:
        from app.agents.travel_agent import _dynamic_instructions

        class FakeUser:
            full_name = "Tester"
            phone = "+213600000000"
            role = "traveler"

        class FakeCtx:
            def __init__(self, deps):
                self.deps = deps

        deps = TravelAgentDeps(user=FakeUser(), db=None, profile_context=profile_context)
        return _dynamic_instructions(prompt_name)(FakeCtx(deps))

    def test_profile_reaches_all_five_agents(self):
        block = render(
            UserProfile(
                user_id=uuid.uuid4(),
                budget_level="budget",
                interests=["history"],
                home_wilaya_id=31,
            ),
            wilaya_name="Oran",
        )
        for name in (
            "travel_agent.main",
            "travel_agent.itinerary",
            "travel_agent.search",
            "travel_agent.transport",
            "travel_agent.events",
        ):
            prompt = self._render(name, block)
            assert "TRAVELER PROFILE" in prompt, name
            assert "Budget: budget" in prompt, name

    def test_empty_profile_adds_nothing(self):
        prompt = self._render("travel_agent.main", "")
        assert "TRAVELER PROFILE" not in prompt


class TestProfileApi:
    async def test_get_profile_defaults_empty(self, client, auth_headers, db, test_user):
        resp = await client.get("/api/v1/users/me/traveler-profile", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == str(test_user.id)
        assert body["budget_level"] is None
        assert body["home_wilaya_id"] is None

    async def test_get_requires_auth(self, client):
        resp = await client.get("/api/v1/users/me/traveler-profile")
        assert resp.status_code in (401, 403)

    async def test_put_updates_profile(self, client, auth_headers):
        resp = await client.put(
            "/api/v1/users/me/traveler-profile",
            json={
                "budget_level": "luxury",
                "interests": ["history", "food"],
                "home_wilaya_id": 25,
                "travel_style": "cultural",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_level"] == "luxury"
        assert set(body["interests"]) == {"history", "food"}
        assert body["home_wilaya_id"] == 25
        assert body["home_wilaya_name"] == "Constantine"
        assert body["travel_style"] == "cultural"

    async def test_put_validates_enum(self, client, auth_headers):
        resp = await client.put(
            "/api/v1/users/me/traveler-profile",
            json={"budget_level": "extreme"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_put_partial_update(self, client, auth_headers):
        await client.put(
            "/api/v1/users/me/traveler-profile",
            json={"budget_level": "budget"},
            headers=auth_headers,
        )
        resp = await client.put(
            "/api/v1/users/me/traveler-profile",
            json={"travel_style": "solo"},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["budget_level"] == "budget"
        assert body["travel_style"] == "solo"

    async def test_get_reflects_persisted_profile(self, client, auth_headers):
        await client.put(
            "/api/v1/users/me/traveler-profile",
            json={"home_wilaya_id": 16},
            headers=auth_headers,
        )
        resp = await client.get("/api/v1/users/me/traveler-profile", headers=auth_headers)
        assert resp.json()["home_wilaya_id"] == 16
        assert resp.json()["home_wilaya_name"] == "Alger"
