"""
AgentLens — Example 2: Multi-step agent with chains, errors, and async calls.

Demonstrates:
  - Nested chains
  - Manual instrumentation (start_call / end_call)
  - Async tool support
  - Error tracking
  - JSON export + re-loading with `agentlens view`

Run:
    cd examples/
    python multi_step_agent.py
"""

import sys
import time
import asyncio
import random

sys.path.insert(0, "../python")

from agentlens import Profiler
from agentlens.profiler import TokenUsage
from agentlens.reporter import Reporter


profiler = Profiler(name="multi-step-agent", tags=["async", "demo"])
reporter = Reporter(profiler)


# ── Tools ─────────────────────────────────────────────────────

@profiler.tool("lookup_database", tags=["storage"])
def lookup_database(entity_id: str) -> dict | None:
    time.sleep(random.uniform(0.02, 0.06))
    if entity_id.startswith("MISSING_"):
        return None
    return {"id": entity_id, "name": f"Entity-{entity_id}", "score": random.random()}


@profiler.tool("validate_schema", tags=["validation"])
def validate_schema(data: dict) -> bool:
    time.sleep(random.uniform(0.005, 0.02))
    if not data.get("id") or not data.get("name"):
        raise ValueError(f"Schema validation failed: missing required fields in {data}")
    return True


@profiler.tool("write_report", tags=["output"])
def write_report(content: str, path: str) -> str:
    time.sleep(random.uniform(0.01, 0.04))
    return f"Report written to {path} ({len(content)} bytes)"


# ── Async tool ────────────────────────────────────────────────

@profiler.tool("async_api_call", tags=["external"])
async def async_api_call(endpoint: str, payload: dict) -> dict:
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if "timeout" in endpoint:
        raise TimeoutError(f"Request to {endpoint} timed out")
    return {"status": 200, "data": {"endpoint": endpoint, "payload_size": len(str(payload))}}


# ── Manual LLM instrumentation (no decorator needed) ──────────

async def call_llm_manual(prompt: str, model: str = "claude-opus-4-5") -> str:
    """Shows manual start_call / end_call instrumentation."""
    call = profiler.start_call(f"anthropic/{model}", call_type="llm", model=model)
    try:
        # Simulate LLM call
        await asyncio.sleep(random.uniform(0.4, 1.0))
        response_text = f"[LLM response to: {prompt[:40]}...]"

        profiler.end_call(
            call,
            success=True,
            token_usage=TokenUsage(
                prompt_tokens=random.randint(100, 400),
                completion_tokens=random.randint(50, 150),
                total_tokens=0,  # will sum
            ),
        )
        # Fix total
        call.token_usage.total_tokens = (
            call.token_usage.prompt_tokens + call.token_usage.completion_tokens
        )
        return response_text
    except Exception as exc:
        profiler.end_call(call, success=False, error=exc)
        raise


# ── Agent pipeline ────────────────────────────────────────────

async def run_pipeline(entity_ids: list[str]) -> None:
    print(f"\n  Running multi-step agent on {len(entity_ids)} entities\n")

    async with profiler.chain("full_pipeline"):

        # Phase 1: data retrieval chain
        async with profiler.chain("data_retrieval"):
            records = []
            for eid in entity_ids:
                record = lookup_database(eid)
                if record:
                    records.append(record)
                else:
                    print(f"  [warn] Entity {eid} not found — skipping")

        print(f"  Retrieved {len(records)} records")

        # Phase 2: validation chain (one will fail)
        async with profiler.chain("validation"):
            valid_records = []
            for record in records:
                try:
                    if validate_schema(record):
                        valid_records.append(record)
                except ValueError as e:
                    print(f"  [warn] {e}")

        print(f"  {len(valid_records)} records passed validation")

        # Phase 3: async API calls (one endpoint will timeout)
        async with profiler.chain("external_enrichment"):
            tasks = []
            for record in valid_records:
                endpoint = (
                    "https://api.example.com/enrich"
                    if record["score"] > 0.3
                    else "https://api.example.com/timeout/enrich"
                )
                tasks.append(async_api_call(endpoint, record))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    print(f"  [warn] API call error: {r}")

        # Phase 4: LLM synthesis
        async with profiler.chain("llm_synthesis"):
            summary = await call_llm_manual(
                f"Synthesize findings for {len(valid_records)} entities: "
                + ", ".join(r["name"] for r in valid_records[:3])
            )

        # Phase 5: write output
        write_report(summary, "output/report.md")

    print("\n  Pipeline complete.")


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    entity_ids = [
        "ENT_001", "ENT_002", "MISSING_003", "ENT_004", "ENT_005",
    ]

    asyncio.run(run_pipeline(entity_ids))

    print("\n" + "=" * 60)
    print("  AGENTLENS REPORT")
    print("=" * 60)

    reporter.print_table()
    reporter.print_summary()
    reporter.print_timeline()

    reporter.export_json("multi_step_trace.json")

    print("\n  Stats breakdown:")
    llm_calls = profiler.get_calls(call_type="llm")
    tool_calls = profiler.get_calls(call_type="tool")
    failed = profiler.get_calls(failed_only=True)
    print(f"    LLM calls  : {len(llm_calls)}")
    print(f"    Tool calls : {len(tool_calls)}")
    print(f"    Failed     : {len(failed)}")
    if failed:
        for f in failed:
            print(f"      • {f.name}: {f.error_type} — {f.error}")
