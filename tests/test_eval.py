"""Tests for the agent eval framework — golden set + scoring."""

from app.agents.eval import (
    GOLDEN_SET,
    QUICK_SET,
    EvalCase,
    EvalResult,
    generate_report,
    score_response,
)


class TestGoldenSet:
    def test_golden_set_has_cases(self):
        assert len(GOLDEN_SET) >= 50

    def test_quick_set_smaller(self):
        assert len(QUICK_SET) == 5
        assert len(QUICK_SET) < len(GOLDEN_SET)

    def test_all_cases_have_ids(self):
        ids = [c.id for c in GOLDEN_SET]
        assert len(ids) == len(set(ids)), "Duplicate case IDs"

    def test_all_cases_have_required_fields(self):
        for case in GOLDEN_SET:
            assert case.id
            assert case.name
            assert case.input
            assert case.category in ("general", "search", "planning", "transport")
            assert case.difficulty in ("easy", "medium", "hard")

    def test_categories_covered(self):
        cats = {c.category for c in GOLDEN_SET}
        assert "search" in cats
        assert "transport" in cats
        assert "planning" in cats

    def test_difficulties_covered(self):
        diffs = {c.difficulty for c in GOLDEN_SET}
        assert "easy" in diffs
        assert "medium" in diffs
        assert "hard" in diffs


class TestScoring:
    def test_perfect_match(self):
        case = EvalCase(
            id="test1",
            name="test",
            input="test",
            expected_tools=["search_pois"],
            must_mention=["Tlemcen"],
        )
        result = score_response(case, "Here are historical sites in Tlemcen", ["search_pois"])
        assert result.passed
        assert result.score >= 0.9
        assert result.tools_correct
        assert result.mentions_correct

    def test_wrong_tools(self):
        case = EvalCase(
            id="test2",
            name="test",
            input="test",
            expected_tools=["search_pois", "get_weather"],
            must_mention=[],
        )
        result = score_response(case, "Here are results", ["search_pois"])
        assert not result.tools_correct

    def test_missing_mention(self):
        case = EvalCase(
            id="test3",
            name="test",
            input="test",
            expected_tools=[],
            must_mention=["Algiers"],
        )
        result = score_response(case, "Here are results for Oran", [])
        assert not result.mentions_correct

    def test_forbidden_mention(self):
        case = EvalCase(
            id="test4",
            name="test",
            input="test",
            expected_tools=[],
            must_not_mention=["I don't know"],
        )
        result = score_response(case, "I don't know the answer to that", [])
        assert result.mentions_wrong
        assert not result.passed  # score < 0.6 due to forbidden mention penalty

    def test_length_violation(self):
        case = EvalCase(
            id="test5",
            name="test",
            input="test",
            expected_tools=[],
            max_length=10,
        )
        result = score_response(case, "This is a very long response that exceeds the limit", [])
        assert not result.length_ok

    def test_no_tools_expected(self):
        case = EvalCase(
            id="test6",
            name="test",
            input="test",
            expected_tools=[],
            must_mention=[],
        )
        result = score_response(case, "Any response works", [])
        assert result.passed
        assert result.score == 1.0

    def test_error_result(self):
        result = EvalResult(
            case_id="err",
            case_name="error case",
            passed=False,
            score=0.0,
            duration_ms=100.0,
            error="Connection failed",
        )
        assert not result.passed
        assert result.error == "Connection failed"


class TestReport:
    def test_empty_report(self):
        report = generate_report([])
        assert report.total == 0
        assert report.avg_score == 0.0

    def test_all_passing(self):
        results = [
            EvalResult(
                case_id=f"c{i}", case_name=f"case {i}", passed=True, score=1.0, duration_ms=100
            )
            for i in range(5)
        ]
        report = generate_report(results)
        assert report.total == 5
        assert report.passed == 5
        assert report.failed == 0
        assert report.avg_score == 1.0

    def test_mixed_results(self):
        results = [
            EvalResult(case_id="c1", case_name="pass", passed=True, score=0.9, duration_ms=100),
            EvalResult(case_id="c2", case_name="fail", passed=False, score=0.3, duration_ms=200),
        ]
        report = generate_report(results)
        assert report.total == 2
        assert report.passed == 1
        assert report.failed == 1
        assert 0.5 < report.avg_score < 0.7

    def test_tool_accuracy(self):
        results = [
            EvalResult(
                case_id="c1",
                case_name="c1",
                passed=True,
                score=1.0,
                duration_ms=100,
                tools_called=["search_pois"],
                tools_correct=True,
            ),
            EvalResult(
                case_id="c2",
                case_name="c2",
                passed=True,
                score=0.8,
                duration_ms=100,
                tools_called=["search_pois"],
                tools_correct=False,
            ),
        ]
        report = generate_report(results)
        assert report.tool_accuracy == 0.5
