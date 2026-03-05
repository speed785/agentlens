"""
AgentLens — Example 1: Basic Python usage with simulated tool + LLM calls.

Run:
    cd examples/
    python basic_python.py
"""

import sys
import time
import random

# Add the python package to the path (for running from the repo)
sys.path.insert(0, "../python")

from agentlens import Profiler
from agentlens.reporter import Reporter


# ── Setup ─────────────────────────────────────────────────────

profiler = Profiler(name="research-agent", tags=["example", "demo"])
reporter = Reporter(profiler)


# ── Simulated tool functions ──────────────────────────────────

@profiler.tool("web_search")
def web_search(query: str) -> list[dict]:
    """Simulate a web search tool call."""
    time.sleep(random.uniform(0.05, 0.15))
    return [
        {"title": f"Result 1 for {query}", "url": "https://example.com/1"},
        {"title": f"Result 2 for {query}", "url": "https://example.com/2"},
    ]


@profiler.tool("fetch_page")
def fetch_page(url: str) -> str:
    """Simulate fetching and parsing a web page."""
    time.sleep(random.uniform(0.08, 0.25))
    if "fail" in url:
        raise ConnectionError(f"Failed to fetch {url}")
    return f"<article>Content from {url}</article>"


@profiler.tool("summarize_text")
def summarize_text(text: str) -> str:
    """Simulate a local text summarization step."""
    time.sleep(random.uniform(0.01, 0.03))
    return f"Summary: {text[:80]}..."


# ── Simulated LLM call ────────────────────────────────────────

class FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class FakeLLMResponse:
    """Mimics the shape of an OpenAI ChatCompletion response."""
    def __init__(self, content: str, model: str, prompt_tokens: int, completion_tokens: int):
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": content})()})()]
        self.model = model
        self.usage = FakeUsage(prompt_tokens, completion_tokens)


@profiler.llm(model="gpt-4o", name="plan_research")
def call_llm(messages: list) -> FakeLLMResponse:
    """Simulate calling an LLM to plan or synthesize research."""
    time.sleep(random.uniform(0.3, 0.8))
    return FakeLLMResponse(
        content="Here is my research plan: first search, then fetch, then summarize.",
        model="gpt-4o",
        prompt_tokens=random.randint(200, 500),
        completion_tokens=random.randint(50, 200),
    )


# ── Run a simulated agent pipeline ────────────────────────────

def run_agent(query: str) -> None:
    print(f"\n  Running research agent for: '{query}'\n")

    with profiler.chain("research_pipeline"):
        # Step 1: Ask LLM to plan
        plan_response = call_llm([
            {"role": "system", "content": "You are a research assistant."},
            {"role": "user", "content": f"Plan how to research: {query}"},
        ])

        # Step 2: Execute search
        results = web_search(query)
        print(f"  Found {len(results)} results")

        # Step 3: Fetch each result (one will fail)
        pages = []
        for i, result in enumerate(results):
            url = result["url"] if i == 0 else "https://fail.example.com"
            try:
                page = fetch_page(url)
                pages.append(page)
            except ConnectionError as e:
                print(f"  [warn] {e}")

        # Step 4: Summarize
        for page in pages:
            summary = summarize_text(page)
            print(f"  {summary[:60]}")


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    run_agent("latest advances in AI agent frameworks")

    print("\n" + "=" * 60)
    print("  AGENTLENS REPORT")
    print("=" * 60)

    reporter.print_table()
    reporter.print_summary()
    reporter.print_timeline()

    # Export JSON trace
    reporter.export_json("trace_output.json")
    print("\n  Tip: run `python -m agentlens view trace_output.json` to re-view!")
