# AgentLens 🔬

> **DevTools for AI agents.** Drop-in observability that measures where time is *actually* being spent in your agent pipelines — latency per step, token usage, tool call success/failure rates, and full call chains.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](python/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue?logo=typescript&logoColor=white)](typescript/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)](python/requirements.txt)

```
  Call Trace — research-agent
  ────────────────────────────────────────────────────────────────────────────
  #   │Name                        │Type   │Model           │Latency (ms) │Tokens  │Status
  ────┼────────────────────────────┼───────┼────────────────┼─────────────┼────────┼──────────
  1   │research_pipeline           │chain  │—               │1243.2       │—       │✓ ok
  2   │plan_research               │llm    │gpt-4o          │612.4        │487     │✓ ok
  3   │web_search                  │tool   │—               │87.1         │—       │✓ ok
  4   │fetch_page                  │tool   │—               │134.5        │—       │✓ ok
  5   │fetch_page                  │tool   │—               │12.3         │—       │✗ ConnectionE…
  6   │summarize_text              │tool   │—               │18.9         │—       │✓ ok
  ────┴────────────────────────────┴───────┴────────────────┴─────────────┴────────┴──────────

  AgentLens — Profiler: research-agent
  ──────────────────────────────────────────────────
  Total calls:                   6
    LLM calls:                   1
    Tool calls:                  4
    Failed calls:                1
  Success rate:                  83.3%
  Total latency:                 865.2 ms
  Avg latency:                   144.2 ms
  ──────────────────────────────────────────────────
  Prompt tokens:                 312
  Completion tokens:             175
  Total tokens:                  487
```

---

## Why AgentLens?

When your agent breaks or runs slowly, good luck figuring out *which* tool call failed, *which* LLM call consumed most of your tokens, or *where* latency piled up. `print()` statements and raw logs won't cut it.

AgentLens gives you:

- **Per-call latency** — know exactly which step is slow
- **Token accounting** — prompt vs. completion tokens per LLM call, with totals
- **Success/failure tracking** — error types surfaced immediately
- **Call chains** — group related calls into named pipelines
- **Zero required dependencies** — works with anything that returns a value
- **Drop-in SDK wrappers** — `ProfiledOpenAI` and `ProfiledAnthropic` require zero code changes
- **JSON export** — pipe traces to any logging system or replay them with `agentlens view`

---

## Quick Start

### Python

```bash
pip install agentlens
# With SDK integrations:
pip install agentlens[openai]       # OpenAI
pip install agentlens[anthropic]    # Anthropic
pip install agentlens[all]          # Both
```

```python
from agentlens import Profiler
from agentlens.reporter import Reporter

profiler = Profiler("my-agent")
reporter = Reporter(profiler)

# Decorate tool functions
@profiler.tool("web_search")
def web_search(query: str) -> list:
    ...

# Decorate LLM calls
@profiler.llm(model="gpt-4o")
def call_gpt(messages: list):
    return openai_client.chat.completions.create(model="gpt-4o", messages=messages)

# Group calls into named chains
with profiler.chain("research_pipeline"):
    results = web_search("AI agent frameworks")
    response = call_gpt([{"role": "user", "content": "Summarize: " + str(results)}])

# Print a report
reporter.print_table()
reporter.print_summary()
reporter.export_json("trace.json")
```

#### Drop-in OpenAI wrapper

```python
import openai
from agentlens import Profiler
from agentlens.integrations.openai import ProfiledOpenAI

profiler = Profiler("gpt-agent")
client = ProfiledOpenAI(openai.OpenAI(api_key="..."), profiler=profiler)

# Use it exactly like a normal OpenAI client — profiling is automatic
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

#### Drop-in Anthropic wrapper

```python
import anthropic
from agentlens import Profiler
from agentlens.integrations.anthropic import ProfiledAnthropic

profiler = Profiler("claude-agent")
client = ProfiledAnthropic(anthropic.Anthropic(api_key="..."), profiler=profiler)

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
```

---

### TypeScript / Node.js

```bash
npm install agentlens
# or: yarn add agentlens
```

```typescript
import { Profiler } from "agentlens";
import { Reporter } from "agentlens";

const profiler = new Profiler("my-agent");
const reporter = new Reporter(profiler);

// Wrap tool functions
const searchWeb = profiler.wrapTool("search_web", async (query: string) => {
  const results = await fetch(`https://api.search.com?q=${query}`);
  return results.json();
});

// Wrap LLM calls — token usage extracted automatically
const callGPT = profiler.wrapLLM("gpt-4o", async (messages) => {
  return openai.chat.completions.create({ model: "gpt-4o", messages });
}, { name: "plan_step" });

// Group into chains
await profiler.runChain("research_pipeline", async () => {
  const results = await searchWeb("AI agent frameworks");
  const plan = await callGPT([{ role: "user", content: JSON.stringify(results) }]);
  return plan;
});

reporter.printTable();
reporter.printSummary();
reporter.exportJSON("trace.json");
```

#### Drop-in OpenAI wrapper (TypeScript)

```typescript
import OpenAI from "openai";
import { Profiler } from "agentlens";
import { ProfiledOpenAI } from "agentlens/integrations/openai";

const profiler = new Profiler("gpt-agent");
const openai = new ProfiledOpenAI(new OpenAI({ apiKey: "..." }), profiler);

// Normal usage — fully instrumented
const res = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello!" }],
});
```

---

## Manual Instrumentation

For cases where decorators don't fit:

```python
# Python
call = profiler.start_call("custom_step", call_type="tool")
try:
    result = do_something()
    profiler.end_call(call, success=True)
except Exception as e:
    profiler.end_call(call, success=False, error=e)
```

```typescript
// TypeScript
const call = profiler.startCall("custom_step", "tool");
try {
  const result = await doSomething();
  profiler.endCall(call, { success: true });
} catch (err) {
  profiler.endCall(call, { success: false, error: err as Error });
}
```

---

## CLI Viewer

Replay any exported trace file in the terminal:

```bash
# Python (after pip install agentlens)
agentlens view trace.json
agentlens view trace.json --timeline

# or
python -m agentlens view trace.json
```

---

## API Reference

### `Profiler`

| Method | Description |
|--------|-------------|
| `Profiler(name, tags?)` | Create a profiler instance |
| `.tool(name?, tags?)` | Decorator for tool functions |
| `.llm(model?, name?, tags?)` | Decorator for LLM calls |
| `.chain(name)` | Context manager to group calls |
| `.start_call(name, call_type, model?)` | Manual: start a call |
| `.end_call(call, success, error?, token_usage?)` | Manual: finish a call |
| `.calls` | List of all `ProfiledCall` objects |
| `.summary()` | Dict of aggregate stats |
| `.get_calls(call_type?, success_only?, failed_only?)` | Filtered call list |
| `.clear()` | Reset recorded calls |

### `Reporter`

| Method | Description |
|--------|-------------|
| `Reporter(profiler)` | Create a reporter |
| `.print_table()` | Print a detailed call table |
| `.print_summary()` | Print aggregate statistics |
| `.print_timeline()` | Print ASCII latency timeline |
| `.export_json(path)` | Export full trace as JSON |

---

## Project Structure

```
agentlens/
├── python/
│   └── agentlens/
│       ├── __init__.py
│       ├── profiler.py          # Core: ProfiledCall, Profiler, decorators
│       ├── reporter.py          # CLI table, summary, JSON export
│       ├── __main__.py          # `agentlens view` CLI
│       └── integrations/
│           ├── openai.py        # ProfiledOpenAI drop-in wrapper
│           └── anthropic.py     # ProfiledAnthropic drop-in wrapper
├── typescript/
│   ├── src/
│   │   ├── index.ts             # Package entry point
│   │   ├── profiler.ts          # Core: ProfiledCall, Profiler, wrappers
│   │   ├── reporter.ts          # CLI table, summary, JSON export
│   │   └── integrations/
│   │       ├── openai.ts        # ProfiledOpenAI wrapper
│   │       └── anthropic.ts     # ProfiledAnthropic wrapper
│   ├── package.json
│   └── tsconfig.json
└── examples/
    ├── basic_python.py          # Python: decorators + profiler chain
    ├── multi_step_agent.py      # Python: async, nested chains, error tracking
    └── basic_typescript.ts      # TypeScript: wrapTool + wrapLLM + chain
```

---

## Contributing

Pull requests welcome. To get started:

```bash
git clone https://github.com/speed785/agentlens
cd agentlens

# Python dev setup
cd python && pip install -e ".[dev]"

# TypeScript dev setup
cd typescript && npm install && npm run build
```

---

## License

MIT — see [LICENSE](LICENSE).
