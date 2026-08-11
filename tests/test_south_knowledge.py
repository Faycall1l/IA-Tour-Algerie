"""Tests for the south-Algeria agent knowledge briefing."""

from app.agents.south_knowledge import (
    is_south_query,
    last_user_turn,
    load_south_knowledge,
    south_briefing,
)


class TestSouthKnowledge:
    def test_load_knowledge_covers_all_southern_wilayas(self):
        kb = load_south_knowledge()
        assert len(kb["wilayas"]) == 13
        assert "56" in kb["wilayas"]  # Djanet
        assert kb["wilayas"]["56"]["name"] == "Djanet"

    def test_load_knowledge_has_real_data(self):
        kb = load_south_knowledge()
        djanet = kb["wilayas"]["56"]
        # flights reachable in the DB
        assert any("Djanet" in f for f in djanet["flights"])
        # stays are real rows with prices
        assert all("price_dzd" in s for s in djanet["stays"])

    def test_south_query_detection(self):
        for q in (
            "how do I get to Djanet from Algiers?",
            "desert itinerary through Tamanrasset and the Hoggar",
            "où manger à Timimoun",
            "what to do in Ghardaïa",
        ):
            assert is_south_query(q), q
        for q in (
            "beaches in Oran",
            "hotels near Timgad",
            "restaurants in Alger centre",
        ):
            assert not is_south_query(q), q

    def test_briefing_only_for_south_queries(self):
        assert south_briefing("beaches in Oran") == ""
        brief = south_briefing("trip to Djanet and Tassili n'Ajjer")
        assert "SOUTH ALGERIA BRIEFING" in brief
        assert "Djanet" in brief
        assert "Air Algérie" in brief
        assert "no train" in brief.lower()

    def test_briefing_is_grounded_not_fabricated(self):
        brief = south_briefing("tamanrasset")
        # intro + operator notes + per-wilaya section
        assert "DB-derived" in brief
        assert "Per-wilaya" in brief


class TestLastUserTurn:
    def test_extracts_last_user_message(self):
        history = (
            "\n\n--- PREVIOUS CONVERSATION ---\n"
            "[User]: first question\n"
            "[Assistant]: first answer\n"
            "[User]: how do I get to Djanet?\n"
            "--- END PREVIOUS CONVERSATION ---\n"
        )
        assert last_user_turn(history) == "how do I get to Djanet?"

    def test_empty_history(self):
        assert last_user_turn("") == ""
        assert last_user_turn(None) == ""

    def test_no_user_turn(self):
        assert last_user_turn("[Assistant]: hi there") == ""
