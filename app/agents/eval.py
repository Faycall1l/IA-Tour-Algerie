"""Agent eval framework — golden set + scoring for agent quality.

The golden set defines real travel questions with expected tool calls
and quality criteria. Each eval run scores agent responses against
these criteria, producing a quality report.

Usage:
    python -m app.agents.eval          # Run all evals
    python -m app.agents.eval --quick  # Run quick set (5 cases)
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("athar.agent.eval")


@dataclass
class EvalCase:
    """A single eval case — travel question with expected behavior."""

    id: str
    name: str
    input: str
    expected_tools: list[str] = field(default_factory=list)
    any_of_tools: list[str] = field(default_factory=list)  # At least one of these must be called
    must_mention: list[str] = field(default_factory=list)
    must_not_mention: list[str] = field(default_factory=list)
    max_length: int = 2000
    category: str = "general"  # general, search, planning, transport
    difficulty: str = "easy"  # easy, medium, hard


# ── Tool equivalence groups (interchangeable for scoring) ──
_TOOL_EQUIVALENCE = {
    "search_pois": {"search_pois", "search_experiences", "get_wilaya_guide"},
    "search_stays": {"search_stays"},
    "search_artisans": {"search_artisans"},
    "search_experiences": {"search_experiences", "search_pois"},
    "get_wilaya_guide": {"get_wilaya_guide", "search_pois"},
    "get_transport_route": {"get_transport_route"},
    "get_operator_contacts": {"get_operator_contacts"},
    "get_weather": {"get_weather"},
    "find_events": {"find_events"},
}


@dataclass
class EvalResult:
    """Score for one eval case."""

    case_id: str
    case_name: str
    passed: bool
    score: float  # 0.0 - 1.0
    duration_ms: float
    tools_called: list[str] = field(default_factory=list)
    tools_correct: bool = False
    mentions_correct: bool = False
    mentions_wrong: bool = False
    length_ok: bool = True
    error: str | None = None
    output_preview: str = ""


@dataclass
class EvalReport:
    """Aggregate results from a full eval run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_score: float = 0.0
    avg_duration_ms: float = 0.0
    tool_accuracy: float = 0.0
    results: list[EvalResult] = field(default_factory=list)
    by_category: dict[str, dict] = field(default_factory=dict)
    by_difficulty: dict[str, dict] = field(default_factory=dict)


# ── Golden Set ──

GOLDEN_SET: list[EvalCase] = [
    # Easy — basic search
    EvalCase(
        id="easy_01",
        name="Basic POI search",
        input="Show me historical sites in Tlemcen",
        expected_tools=["search_pois"],
        must_mention=["Tlemcen"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_02",
        name="Weather check",
        input="What's the weather like in Algiers right now?",
        expected_tools=["get_weather"],
        must_mention=["Algiers"],
        category="general",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_03",
        name="Stay search",
        input="I need a hotel in Constantine under 5000 DZD",
        expected_tools=["search_stays"],
        must_mention=["Constantine"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_04",
        name="Events search",
        input="What festivals are happening in Oran this month?",
        expected_tools=["find_events"],
        must_mention=["Oran"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_05",
        name="Artisan search",
        input="Where can I buy traditional pottery in Tlemcen?",
        expected_tools=["search_artisans"],
        must_mention=["Tlemcen"],
        category="search",
        difficulty="easy",
    ),
    # Medium — multi-tool
    EvalCase(
        id="med_01",
        name="Wilaya guide",
        input="What are the must-see attractions in Batna wilaya?",
        expected_tools=["get_wilaya_guide"],
        must_mention=["Batna"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="med_02",
        name="Transport query",
        input="How do I get from Algiers to Oran by train?",
        expected_tools=["get_transport_route"],
        must_mention=["Algiers", "Oran"],
        category="transport",
        difficulty="medium",
    ),
    EvalCase(
        id="med_03",
        name="Multi-category search",
        input="Find me museums and cultural sites in Algiers for kids",
        expected_tools=["search_pois"],
        must_mention=["Algiers"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="med_04",
        name="Operator contacts",
        input="What's the phone number for SNTF customer service?",
        expected_tools=["get_operator_contacts"],
        must_not_mention=["I don't know"],
        category="general",
        difficulty="medium",
    ),
    EvalCase(
        id="med_05",
        name="Accommodation with price",
        input="Find a guesthouse near Timgad ruins, budget-friendly",
        expected_tools=["search_stays"],
        must_mention=["Timgad"],
        category="search",
        difficulty="medium",
    ),
    # Hard — planning / multi-hop
    EvalCase(
        id="hard_01",
        name="Full trip plan",
        input="Plan a 3-day trip to Tlemcen with museums, historical sites, and local food",
        expected_tools=["get_wilaya_guide", "search_pois"],
        must_mention=["Tlemcen"],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_02",
        name="Multi-wilaya transport",
        input="I'm in Algiers and want to visit Oran and Tlemcen in one week. How should I travel between them?",  # noqa: E501
        expected_tools=["get_transport_route"],
        must_mention=["Algiers", "Oran", "Tlemcen"],
        max_length=3000,
        category="transport",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_03",
        name="Sahara adventure planning",
        input="I want to visit the Sahara from Ghardaia. What can I see, where can I sleep, and how do I get around?",  # noqa: E501
        expected_tools=["get_wilaya_guide", "search_stays"],
        must_mention=["Ghardaïa"],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_04",
        name="Budget comparison",
        input="Compare budget vs luxury accommodation options in Algiers. Which neighborhoods have the best value?",  # noqa: E501
        expected_tools=["search_stays"],
        must_mention=["Algiers"],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_05",
        name="Cultural deep dive",
        input="Tell me about Berber culture in Kabylie — what villages should I visit, what crafts can I buy, and what food should I try?",  # noqa: E501
        expected_tools=["get_wilaya_guide", "search_artisans"],
        must_mention=[],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    # ── Easy: more search variants ──
    EvalCase(
        id="easy_06",
        name="Beach search",
        input="Show me the best beaches in Jijel",
        expected_tools=["search_pois"],
        must_mention=["Jijel"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_07",
        name="Museum search",
        input="Are there any museums in Constantine?",
        expected_tools=["search_pois"],
        must_mention=["Constantine"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_08",
        name="Mountain search",
        input="I want to hike in Djurdjura — what trails are there?",
        expected_tools=["search_pois"],
        must_mention=["Djurdjura"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_09",
        name="Religious site search",
        input="Find mosques and religious sites in Tlemcen",
        expected_tools=["search_pois"],
        must_mention=["Tlemcen"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="easy_10",
        name="Stay search by price",
        input="Hotels in Annaba under 4000 DZD per night",
        expected_tools=["search_stays"],
        must_mention=["Annaba"],
        category="search",
        difficulty="easy",
    ),
    # ── Medium: multi-tool combos ──
    EvalCase(
        id="med_06",
        name="Experience search",
        input="What guided tours are available in Algiers?",
        expected_tools=["search_experiences"],
        must_mention=["Algiers"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="med_07",
        name="Taxi route",
        input="Can I take a taxi from Setif to Batna? How much does it cost?",
        expected_tools=["get_transport_route"],
        must_not_mention=["I don't know"],
        category="transport",
        difficulty="medium",
    ),
    EvalCase(
        id="med_08",
        name="Weather + POI combo",
        input="What's the weather in Oran this weekend? Are there outdoor activities I should plan for?",  # noqa: E501
        expected_tools=["get_weather", "search_pois"],
        must_mention=["Oran"],
        category="general",
        difficulty="medium",
    ),
    EvalCase(
        id="med_09",
        name="Food search",
        input="Where can I find the best couscous in Algiers?",
        expected_tools=["search_pois"],
        must_mention=["Algiers"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="med_10",
        name="Park search",
        input="What national parks are near Tizi Ouzou?",
        expected_tools=["search_pois"],
        must_mention=["Tizi Ouzou"],
        category="search",
        difficulty="medium",
    ),
    # ── Hard: complex planning ──
    EvalCase(
        id="hard_06",
        name="Weekend trip plan",
        input="Plan a weekend trip to Constantine — I love history and want to try local food",
        expected_tools=["get_wilaya_guide", "search_pois"],
        must_mention=["Constantine"],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_07",
        name="Multi-transport comparison",
        input="What are my options to get from Algiers to Ghardaia? Compare train, bus, and flight.",  # noqa: E501
        expected_tools=["get_transport_route"],
        must_mention=["Algiers", "Ghardaïa"],
        max_length=3000,
        category="transport",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_08",
        name="Family trip planning",
        input="I'm planning a family trip to Tlemcen with 2 kids (ages 5 and 10). What should we see and do for 4 days?",  # noqa: E501
        expected_tools=["get_wilaya_guide", "search_pois"],
        must_mention=["Tlemcen"],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_09",
        name="Artisan + cultural tour",
        input="I want to do a craft shopping tour in Tlemcen — pottery, carpets, and leather. Where should I go and how do I get between workshops?",  # noqa: E501
        expected_tools=["search_artisans", "get_transport_route"],
        must_mention=["Tlemcen"],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_10",
        name="Sahara multi-day plan",
        input="I have 5 days starting from Algiers. I want to reach the Sahara desert. Plan my route, stops, and what to see along the way.",  # noqa: E501
        expected_tools=["get_transport_route", "get_wilaya_guide"],
        must_mention=[],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
    # ── Edge cases ──
    EvalCase(
        id="edge_01",
        name="Non-existent wilaya query",
        input="What's in wilaya 99?",
        expected_tools=["search_pois"],
        must_not_mention=["I don't know"],
        category="general",
        difficulty="easy",
    ),
    EvalCase(
        id="edge_02",
        name="Very broad query",
        input="Tell me about Algeria",
        expected_tools=[],
        must_mention=[],
        category="general",
        difficulty="easy",
    ),
    EvalCase(
        id="edge_03",
        name="Specific price range",
        input="Hotels in Oran between 3000 and 6000 DZD with parking",
        expected_tools=["search_stays"],
        must_mention=["Oran"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="edge_04",
        name="Opening hours query",
        input="What time does the National Museum of Algiers open?",
        expected_tools=["search_pois"],
        must_mention=[],
        category="general",
        difficulty="medium",
    ),
    EvalCase(
        id="edge_05",
        name="Operator phone number",
        input="How do I contact Air Algérie for flight bookings?",
        expected_tools=["get_operator_contacts"],
        must_not_mention=["I don't know"],
        category="general",
        difficulty="easy",
    ),
    # ── Transport-specific ──
    EvalCase(
        id="trans_01",
        name="Train schedule",
        input="What time does the last train leave Algiers for Oran?",
        expected_tools=["get_transport_route"],
        must_mention=["Algiers", "Oran"],
        category="transport",
        difficulty="medium",
    ),
    EvalCase(
        id="trans_02",
        name="Bus alternative",
        input="If there's no train from Setif to Constantine, what are my options?",
        expected_tools=["get_transport_route"],
        must_mention=["Sétif", "Constantine"],
        category="transport",
        difficulty="medium",
    ),
    EvalCase(
        id="trans_03",
        name="Flight search",
        input="Are there flights from Algiers to Bechar?",
        expected_tools=["get_transport_route"],
        must_mention=["Béchar"],
        category="transport",
        difficulty="medium",
    ),
    # ── Events-specific ──
    EvalCase(
        id="evt_01",
        name="Festival by month",
        input="What cultural festivals happen in Tlemcen in July?",
        expected_tools=["find_events"],
        must_mention=["Tlemcen"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="evt_02",
        name="Events in wilaya",
        input="Are there any events in Djemila or Setif this summer?",
        expected_tools=["find_events"],
        must_mention=[],
        category="search",
        difficulty="medium",
    ),
    # ── Artisan-specific ──
    EvalCase(
        id="art_01",
        name="Carpet shopping",
        input="Where can I buy traditional Algerian carpets in Tlemcen?",
        expected_tools=["search_artisans"],
        must_mention=["Tlemcen"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="art_02",
        name="Jewelry artisans",
        input="I'm looking for traditional Kabyle jewelry — which artisans should I visit?",
        expected_tools=["search_artisans"],
        must_mention=[],
        category="search",
        difficulty="medium",
    ),
    # ── Hard multi-hop ──
    EvalCase(
        id="hard_11",
        name="Coastal road trip",
        input="I want to drive the Mediterranean coast from Algiers to Annaba over 5 days. Plan my stops with beaches, food, and where to sleep each night.",  # noqa: E501
        expected_tools=["get_transport_route", "search_pois", "search_stays"],
        must_mention=["Algiers", "Annaba"],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_12",
        name="Historical tour",
        input="Plan a historical tour of Algeria — I want to see Roman ruins, Ottoman sites, and colonial architecture. Give me a 7-day itinerary.",  # noqa: E501
        expected_tools=["search_pois", "get_wilaya_guide"],
        must_mention=[],
        max_length=5000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_13",
        name="Budget backpacking",
        input="I have a tight budget of 3000 DZD per day. I want to travel from Oran to Tlemcen, see the main sights, eat local food, and find cheap accommodation.",  # noqa: E501
        expected_tools=["get_transport_route", "search_pois", "search_stays"],
        must_mention=["Oran", "Tlemcen"],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_14",
        name="Winter Sahara trip",
        input="Is it a good idea to visit the Sahara in December? What's the weather like, and where should I stay in Djanet?",  # noqa: E501
        expected_tools=["get_weather", "search_stays", "get_wilaya_guide"],
        must_mention=["Djanet"],
        max_length=3000,
        category="planning",
        difficulty="hard",
    ),
    EvalCase(
        id="hard_15",
        name="Photography tour",
        input="I'm a photographer and want to capture Algeria's most photogenic spots. Plan a 10-day trip focusing on landscapes, architecture, and street photography.",  # noqa: E501
        expected_tools=["search_pois", "get_wilaya_guide"],
        must_mention=[],
        max_length=5000,
        category="planning",
        difficulty="hard",
    ),
    # ── Final 3 to reach 50 ──
    EvalCase(
        id="easy_11",
        name="Cafe search",
        input="Where can I find a good cafe in Blida?",
        expected_tools=["search_pois"],
        must_mention=["Blida"],
        category="search",
        difficulty="easy",
    ),
    EvalCase(
        id="med_11",
        name="Nightlife/restaurants",
        input="What are the best restaurants in Algiers for seafood?",
        expected_tools=["search_pois"],
        must_mention=["Algiers"],
        category="search",
        difficulty="medium",
    ),
    EvalCase(
        id="hard_16",
        name="Wedding venue planning",
        input="I'm getting married in Tlemcen. Can you find traditional venues, nearby hotels for guests, and artisan shops for decorations?",  # noqa: E501
        expected_tools=["search_pois", "search_stays", "search_artisans"],
        must_mention=["Tlemcen"],
        max_length=4000,
        category="planning",
        difficulty="hard",
    ),
]

QUICK_SET = GOLDEN_SET[:5]


# ── Scoring ──


def score_response(case: EvalCase, output: str, tools_called: list[str]) -> EvalResult:
    """Score a single agent response against the eval case criteria."""
    duration_ms = 0.0
    output_str = str(output)

    # Tool accuracy — with equivalence tolerance
    tools_correct = True
    if case.expected_tools:
        tools_correct = all(
            t in tools_called
            or any(
                tools_called_item in _TOOL_EQUIVALENCE.get(t, set())
                for tools_called_item in tools_called
            )
            for t in case.expected_tools
        )

    # Must mention
    output_lower = output_str.lower()
    mentions_correct = all(m.lower() in output_lower for m in case.must_mention)

    # Must not mention
    mentions_wrong = any(m.lower() in output_lower for m in case.must_not_mention)

    # Length check
    length_ok = len(output_str) <= case.max_length

    # Overall score
    scores = []
    if case.expected_tools:
        scores.append(1.0 if tools_correct else 0.5)
    if case.must_mention:
        scores.append(1.0 if mentions_correct else 0.3)
    if case.must_not_mention:
        scores.append(0.0 if mentions_wrong else 1.0)
    scores.append(1.0 if length_ok else 0.5)

    score = sum(scores) / len(scores) if scores else 1.0
    passed = score >= 0.6

    return EvalResult(
        case_id=case.id,
        case_name=case.name,
        passed=passed,
        score=round(score, 3),
        duration_ms=duration_ms,
        tools_called=tools_called,
        tools_correct=tools_correct,
        mentions_correct=mentions_correct,
        mentions_wrong=mentions_wrong,
        length_ok=length_ok,
        output_preview=output_str[:200],
    )


def generate_report(results: list[EvalResult]) -> EvalReport:
    """Aggregate eval results into a summary report."""
    if not results:
        return EvalReport()

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_score = sum(r.score for r in results) / total
    avg_duration = sum(r.duration_ms for r in results) / total

    tools_with_cases = [r for r in results if r.tools_called]
    tool_accuracy = (
        sum(1 for r in tools_with_cases if r.tools_correct) / len(tools_with_cases)
        if tools_with_cases
        else 0.0
    )

    by_category: dict[str, dict] = {}
    by_difficulty: dict[str, dict] = {}

    # We need the original cases to group — store case metadata during eval
    # (simplified: category extraction is intentionally left for a later pass)

    return EvalReport(
        total=total,
        passed=passed,
        failed=total - passed,
        avg_score=round(avg_score, 3),
        avg_duration_ms=round(avg_duration, 1),
        tool_accuracy=round(tool_accuracy, 3),
        results=results,
        by_category=by_category,
        by_difficulty=by_difficulty,
    )


# ── CLI runner ──


async def run_eval(agent=None, cases: list[EvalCase] | None = None, deps=None):
    """Run eval against an agent. Returns EvalReport."""
    if cases is None:
        cases = GOLDEN_SET

    if agent is None:
        logger.warning("No agent provided — returning empty report")
        return EvalReport()

    from app.agents.resilience import tool_call_names

    results: list[EvalResult] = []

    for case in cases:
        start = time.time()
        try:
            result = await agent.run(case.input, deps=deps)
            output = str(result.output)
            duration = (time.time() - start) * 1000

            tools_called = tool_call_names(result)

            eval_result = score_response(case, output, tools_called)
            eval_result.duration_ms = round(duration, 1)
            results.append(eval_result)

        except Exception as e:
            duration = (time.time() - start) * 1000
            results.append(
                EvalResult(
                    case_id=case.id,
                    case_name=case.name,
                    passed=False,
                    score=0.0,
                    duration_ms=round(duration, 1),
                    error=str(e)[:500],
                )
            )

    report = generate_report(results)
    return report


def format_report(report: EvalReport) -> str:
    """Format a report for terminal display."""
    lines = [
        "=" * 60,
        "  ATHAR Agent Eval Report",
        "=" * 60,
        f"  Total: {report.total}  |  Passed: {report.passed}  |  Failed: {report.failed}",
        f"  Avg Score: {report.avg_score:.1%}  |  Tool Accuracy: {report.tool_accuracy:.1%}",
        f"  Avg Duration: {report.avg_duration_ms:.0f}ms",
        "-" * 60,
    ]
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{status}] {r.case_name} (score={r.score:.2f}, {r.duration_ms:.0f}ms)")
        if r.error:
            lines.append(f"         Error: {r.error[:100]}")
        if r.tools_called:
            lines.append(f"         Tools: {', '.join(r.tools_called)}")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run agent eval suite")
    parser.add_argument("--quick", action="store_true", help="Run quick set (5 cases)")
    args = parser.parse_args()

    cases = QUICK_SET if args.quick else GOLDEN_SET
    print(f"Running eval with {len(cases)} cases...")

    # To run: needs agent + deps from app startup
    # python -m app.agents.eval --quick
    print("Tip: import and call run_eval() from app startup code")
    print(f"Golden set has {len(GOLDEN_SET)} cases ({len(QUICK_SET)} in quick set)")
