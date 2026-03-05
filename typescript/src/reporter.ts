/**
 * AgentLens — Reporter: CLI tables, summaries, JSON export.
 */

import * as fs from "fs";
import * as path from "path";
import type { Profiler, ProfiledCall, CallType } from "./profiler";

// ─────────────────────────────────────────────────────────────
// ANSI colours
// ─────────────────────────────────────────────────────────────

const supportsColor = process.stdout.isTTY ?? false;

function ansi(code: string, text: string): string {
  if (!supportsColor) return text;
  return `\x1b[${code}m${text}\x1b[0m`;
}

const c = {
  bold: (t: string) => ansi("1", t),
  green: (t: string) => ansi("32", t),
  red: (t: string) => ansi("31", t),
  yellow: (t: string) => ansi("33", t),
  cyan: (t: string) => ansi("36", t),
  dim: (t: string) => ansi("2", t),
};

function pad(value: string, width: number): string {
  const s = value.slice(0, width);
  return s.padEnd(width);
}

// ─────────────────────────────────────────────────────────────
// Reporter
// ─────────────────────────────────────────────────────────────

export class Reporter {
  constructor(private readonly profiler: Profiler) {}

  // ── Summary ───────────────────────────────────────────────

  printSummary(): void {
    const s = this.profiler.summary();
    const lines: string[] = [];

    const row = (label: string, value: string, colorFn?: (t: string) => string): void => {
      const val = colorFn ? colorFn(value) : value;
      lines.push(`  ${c.dim(label + ":").padEnd(38)} ${val}`);
    };

    lines.push(c.bold(`\n  AgentLens — Profiler: ${s.profiler}`));
    lines.push(c.dim("  " + "─".repeat(46)));
    row("Total calls", String(s.totalCalls));
    row("  LLM calls", String(s.llmCalls), c.cyan);
    row("  Tool calls", String(s.toolCalls));
    row("  Failed calls", String(s.failedCalls), s.failedCalls > 0 ? c.red : undefined);
    row(
      "Success rate",
      `${s.successRate}%`,
      s.successRate === 100 ? c.green : c.yellow,
    );
    row("Total latency", `${s.totalLatencyMs} ms`);
    row("Avg latency", `${s.avgLatencyMs} ms`);
    row("Min / Max latency", `${s.minLatencyMs} ms / ${s.maxLatencyMs} ms`);

    if (s.tokenUsage.totalTokens > 0) {
      lines.push(c.dim("  " + "─".repeat(46)));
      row("Prompt tokens", String(s.tokenUsage.promptTokens), c.dim);
      row("Completion tokens", String(s.tokenUsage.completionTokens), c.dim);
      row("Total tokens", String(s.tokenUsage.totalTokens), c.cyan);
    }

    lines.push("");
    console.log(lines.join("\n"));
  }

  // ── Call table ────────────────────────────────────────────

  printTable(opts: { callType?: CallType; showErrors?: boolean } = {}): void {
    let calls = this.profiler.getCalls({ callType: opts.callType });
    if (opts.showErrors === false) calls = calls.filter((c) => c.success);

    const colW = [4, 28, 7, 16, 13, 8, 10];
    const headers = ["#", "Name", "Type", "Model", "Latency (ms)", "Tokens", "Status"];

    const sep = c.dim("  " + colW.map((w) => "─".repeat(w)).join("┼"));
    const headerRow =
      "  " + headers.map((h, i) => c.bold(pad(h, colW[i]))).join("│");

    console.log(c.bold(`\n  Call Trace — ${this.profiler.name}`));
    console.log(c.dim("  " + colW.map((w) => "─".repeat(w)).join("┬")));
    console.log(headerRow);
    console.log(sep);

    calls.forEach((call, idx) => {
      const latency = call.latencyMs !== null ? `${call.latencyMs.toFixed(1)}` : "—";
      const tokens = call.tokenUsage.totalTokens ? String(call.tokenUsage.totalTokens) : "—";
      const status = call.success ? c.green("✓ ok") : c.red(`✗ ${call.errorType ?? "err"}`);
      const model = call.model ?? "—";
      const typeStr = call.callType;

      const row =
        "  " +
        [
          pad(String(idx + 1), colW[0]),
          pad(call.name, colW[1]),
          c.cyan(pad(typeStr, colW[2])),
          c.dim(pad(model, colW[3])),
          pad(latency, colW[4]),
          pad(tokens, colW[5]),
          status,
        ].join("│");
      console.log(row);
    });

    console.log(c.dim("  " + colW.map((w) => "─".repeat(w)).join("┴")));
    console.log(`  ${calls.length} call(s) recorded\n`);
  }

  // ── ASCII timeline ────────────────────────────────────────

  printTimeline(): void {
    const calls = this.profiler.calls.filter((c) => c.endedAt !== null);
    if (calls.length === 0) {
      console.log("  No calls recorded.");
      return;
    }

    const tMin = Math.min(...calls.map((c) => c.startedAt.getTime()));
    const tMax = Math.max(...calls.map((c) => c.endedAt!.getTime()));
    const totalSpan = tMax - tMin || 1;
    const barWidth = 40;

    console.log(c.bold(`\n  Timeline — ${this.profiler.name}`));
    console.log(c.dim(`  ${"Name".padEnd(28)} ${"Bar".padEnd(42)} ${"ms".padStart(7)}`));
    console.log(c.dim("  " + "─".repeat(80)));

    for (const call of calls) {
      const offset = call.startedAt.getTime() - tMin;
      const width = Math.max(1, Math.round(((call.latencyMs ?? 0) / totalSpan) * barWidth));
      const pad_ = Math.round((offset / totalSpan) * barWidth);
      const barChar = call.success ? "█" : "░";
      const bar = " ".repeat(pad_) + barChar.repeat(width);
      const latencyStr = call.latencyMs !== null ? `${call.latencyMs.toFixed(1)}` : "—";
      const colorFn = call.callType === "llm" ? c.cyan : c.green;
      console.log(
        `  ${call.name.slice(0, 26).padEnd(28)} ${colorFn(bar.padEnd(42))} ${c.dim(latencyStr.padStart(7))}`,
      );
    }
    console.log("");
  }

  // ── JSON export ───────────────────────────────────────────

  exportJSON(filePath: string): void {
    const data = {
      exportedAt: new Date().toISOString(),
      profiler: this.profiler.name,
      summary: this.profiler.summary(),
      calls: this.profiler.calls.map((c) => c.toJSON()),
    };
    const dir = path.dirname(filePath);
    if (dir && dir !== ".") fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), "utf-8");
    console.log(`  Exported ${data.calls.length} call(s) to ${filePath}`);
  }

  toObject(): Record<string, unknown> {
    return {
      exportedAt: new Date().toISOString(),
      profiler: this.profiler.name,
      summary: this.profiler.summary(),
      calls: this.profiler.calls.map((c) => c.toJSON()),
    };
  }
}
