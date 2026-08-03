#!/usr/bin/env python3
"""Run the eval suite against the live vLLM agent.

Usage:
    python -m scripts.eval_live           # Full 50-case eval
    python -m scripts.eval_live --quick   # Quick 5-case smoke test
"""

import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.deps import TravelAgentDeps
from app.agents.eval import GOLDEN_SET, QUICK_SET, EvalCase, EvalResult, generate_report, format_report, score_response
from app.db.session import async_session
from app.models.user import User


def _extract_tool_calls(result) -> list[str]:
    """Extract tool names from PydanticAI run result via message history."""
    tools = []
    try:
        for msg in result.new_messages():
            if hasattr(msg, 'parts'):
                for part in msg.parts:
                    if type(part).__name__ == "ToolCallPart":
                        tools.append(part.tool_name)
    except Exception:
        pass
    return list(dict.fromkeys(tools))  # deduplicate, preserve order


async def run_eval_single(agent, case: EvalCase, deps: TravelAgentDeps) -> EvalResult:
    """Run one eval case and return the result. Retries on transient errors."""
    max_retries = 3
    case_timeout = 120.0  # 120s per case max (vLLM can be slow on complex calls)
    for attempt in range(max_retries):
        start = time.time()
        try:
            result = await asyncio.wait_for(
                agent.run(case.input, deps=deps),
                timeout=case_timeout,
            )
            output = str(result.output)
            duration = (time.time() - start) * 1000

            tools_called = _extract_tool_calls(result)

            eval_result = score_response(case, output, tools_called)
            eval_result.duration_ms = round(duration, 1)
            eval_result.output_preview = output[:500]
            return eval_result

        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            if attempt < max_retries - 1:
                print(f"\n         Timeout (attempt {attempt+1}/{max_retries}), retrying...", end=" ", flush=True)
                await asyncio.sleep(5)
                continue
            return EvalResult(
                case_id=case.id, case_name=case.name, passed=False, score=0.0,
                duration_ms=round(duration, 1), error=f"Timeout after {case_timeout}s",
                output_preview="TIMEOUT",
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            error_str = str(e)
            is_transient = any(code in error_str for code in ["307", "429", "503", "timeout", "Timeout"])
            if is_transient and attempt < max_retries - 1:
                wait = (attempt + 1) * 10
                print(f"\n         Transient error (attempt {attempt+1}/{max_retries}), retrying in {wait}s...", end=" ", flush=True)
                await asyncio.sleep(wait)
                continue

            return EvalResult(
                case_id=case.id,
                case_name=case.name,
                passed=False,
                score=0.0,
                duration_ms=round(duration, 1),
                error=error_str[:500],
                output_preview=f"ERROR: {e}",
            )


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run eval against live vLLM agent")
    parser.add_argument("--quick", action="store_true", help="Run quick set (5 cases)")
    parser.add_argument("--agent", default="travel_agent", help="Agent to test (travel_agent, search_agent)")
    parser.add_argument("--save", action="store_true", help="Save results to JSON")
    args = parser.parse_args()

    cases = QUICK_SET if args.quick else GOLDEN_SET
    print(f"Running {len(cases)} eval cases against {args.agent}...")

    # Create agent
    from app.agents.travel_agent import create_travel_agent, create_search_agent
    from app.core.config import settings

    bu = settings.agent.vllm.base_url
    ak = settings.agent.vllm.api_key
    mn = settings.agent.vllm.model

    if args.agent == "search_agent":
        agent = create_search_agent(base_url=bu, api_key=ak, model_name=mn)
    else:
        agent = create_travel_agent(base_url=bu, api_key=ak, model_name=mn)

    if agent is None:
        print("ERROR: Could not create agent — check ATHAR_AGENT__VLLM settings in .env")
        sys.exit(1)

    # Create deps with a real DB session
    async with async_session() as db:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        )
        row = result.first()
        if not row:
            # Create a temporary user for eval
            print("No admin user found — creating eval user...")
            eval_user = User(phone="0000000000", role="traveler", full_name="Eval Runner")
            db.add(eval_user)
            await db.commit()
            await db.refresh(eval_user)
            user = eval_user
        else:
            user = await db.get(User, row[0])

        deps = TravelAgentDeps(user=user, db=db, request_id="eval-run")

        # Run cases
        results = []
        for i, case in enumerate(cases):
            print(f"  [{i+1}/{len(cases)}] {case.name}...", end=" ", flush=True)
            eval_result = await run_eval_single(agent, case, deps)
            results.append(eval_result)
            status = "PASS" if eval_result.passed else "FAIL"
            tools = f" tools={eval_result.tools_called}" if eval_result.tools_called else ""
            print(f"{status} (score={eval_result.score:.2f}, {eval_result.duration_ms:.0f}ms{tools})")
            if eval_result.error:
                print(f"         Error: {eval_result.error[:120]}")
            # Rate limit: wait between cases to avoid hitting vLLM request_limit
            if i < len(cases) - 1:
                await asyncio.sleep(8.0)

    # Generate report
    from app.agents.eval import EvalReport
    report = EvalReport(
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        avg_score=sum(r.score for r in results) / len(results) if results else 0,
        avg_duration_ms=sum(r.duration_ms for r in results) / len(results) if results else 0,
        tool_accuracy=(
            sum(1 for r in results if r.tools_called and r.tools_correct) /
            max(1, sum(1 for r in results if r.tools_called))
        ),
        results=results,
    )

    print("\n" + format_report(report))

    # Save if requested
    if args.save:
        out_path = Path("eval_results.json")
        data = {
            "agent": args.agent,
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "avg_score": round(report.avg_score, 3),
            "avg_duration_ms": round(report.avg_duration_ms, 1),
            "tool_accuracy": round(report.tool_accuracy, 3),
            "results": [asdict(r) for r in results],
        }
        out_path.write_text(json.dumps(data, indent=2))
        print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
