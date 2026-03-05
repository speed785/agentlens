/**
 * AgentLens — Example 3: TypeScript basic usage.
 *
 * Run (from repo root):
 *   cd typescript && npm install && npm run build
 *   node dist/../../examples/basic_typescript.js
 *
 * Or with ts-node:
 *   cd typescript && npx ts-node ../examples/basic_typescript.ts
 */

import { Profiler } from "../typescript/src/profiler";
import { Reporter } from "../typescript/src/reporter";

const profiler = new Profiler("ts-research-agent", ["typescript", "demo"]);
const reporter = new Reporter(profiler);

// ── Simulated tools ────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const searchWeb = profiler.wrapTool(
  "search_web",
  async (query: string): Promise<Array<{ title: string; url: string }>> => {
    await sleep(50 + Math.random() * 100);
    return [
      { title: `Result 1 for ${query}`, url: "https://example.com/1" },
      { title: `Result 2 for ${query}`, url: "https://example.com/2" },
    ];
  },
);

const fetchPage = profiler.wrapTool(
  "fetch_page",
  async (url: string): Promise<string> => {
    await sleep(80 + Math.random() * 150);
    if (url.includes("fail")) throw new Error(`Failed to fetch ${url}`);
    return `<article>Content from ${url}</article>`;
  },
);

const summarizeText = profiler.wrapTool(
  "summarize_text",
  (text: string): string => {
    return `Summary: ${text.slice(0, 80)}...`;
  },
);

// ── Simulated LLM call ─────────────────────────────────────

interface FakeLLMResponse {
  model: string;
  choices: Array<{ message: { content: string } }>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

const callLLM = profiler.wrapLLM(
  "gpt-4o",
  async (messages: Array<{ role: string; content: string }>): Promise<FakeLLMResponse> => {
    await sleep(300 + Math.random() * 500);
    const prompt = Math.floor(200 + Math.random() * 300);
    const completion = Math.floor(50 + Math.random() * 150);
    return {
      model: "gpt-4o",
      choices: [{ message: { content: "Research plan: search → fetch → summarize." } }],
      usage: {
        prompt_tokens: prompt,
        completion_tokens: completion,
        total_tokens: prompt + completion,
      },
    };
  },
  { name: "plan_research" },
);

// ── Agent pipeline ─────────────────────────────────────────

async function runAgent(query: string): Promise<void> {
  console.log(`\n  Running TS agent for: '${query}'\n`);

  await profiler.runChain("research_pipeline", async () => {
    // Step 1: Plan with LLM
    const plan = await callLLM([
      { role: "system", content: "You are a research assistant." },
      { role: "user", content: `Plan research for: ${query}` },
    ]);
    console.log(`  Plan: ${plan.choices[0].message.content.slice(0, 60)}`);

    // Step 2: Search
    const results = await searchWeb(query);
    console.log(`  Found ${results.length} results`);

    // Step 3: Fetch (second will fail)
    const pages: string[] = [];
    for (let i = 0; i < results.length; i++) {
      const url = i === 0 ? results[i].url : "https://fail.example.com";
      try {
        const page = await fetchPage(url);
        pages.push(page);
      } catch (err) {
        console.log(`  [warn] ${(err as Error).message}`);
      }
    }

    // Step 4: Summarize
    for (const page of pages) {
      const summary = summarizeText(page);
      console.log(`  ${summary.slice(0, 60)}`);
    }
  });
}

// ── Main ──────────────────────────────────────────────────

(async () => {
  await runAgent("latest advances in AI agent frameworks");

  console.log("\n" + "=".repeat(60));
  console.log("  AGENTLENS REPORT (TypeScript)");
  console.log("=".repeat(60));

  reporter.printTable();
  reporter.printSummary();
  reporter.printTimeline();

  reporter.exportJSON("ts_trace_output.json");
})();
