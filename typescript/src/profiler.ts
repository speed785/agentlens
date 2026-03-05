/**
 * AgentLens — Core profiler for TypeScript/Node.js
 * Instruments LLM calls and tool calls: latency, token usage, success/failure.
 */

import { randomUUID } from "crypto";
import {
  AgentLensLogger,
  defaultObservabilityConfig,
  MetricsCollector,
  ObservabilityConfig,
} from "./observability";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export type CallType = "llm" | "tool" | "chain";

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ProfiledCallData {
  id: string;
  name: string;
  callType: CallType;
  startedAt: string; // ISO
  endedAt: string | null;
  latencyMs: number | null;
  success: boolean;
  error: string | null;
  errorType: string | null;
  tokenUsage: TokenUsage;
  model: string | null;
  metadata: Record<string, unknown>;
  parentId: string | null;
  tags: string[];
}

export interface ProfilerSummary {
  profiler: string;
  totalCalls: number;
  llmCalls: number;
  toolCalls: number;
  failedCalls: number;
  successRate: number;
  totalLatencyMs: number;
  avgLatencyMs: number;
  minLatencyMs: number;
  maxLatencyMs: number;
  tokenUsage: TokenUsage;
}

// ─────────────────────────────────────────────────────────────
// ProfiledCall
// ─────────────────────────────────────────────────────────────

export class ProfiledCall {
  readonly id: string;
  name: string;
  callType: CallType;
  startedAt: Date;
  endedAt: Date | null = null;
  latencyMs: number | null = null;
  success: boolean = true;
  error: string | null = null;
  errorType: string | null = null;
  tokenUsage: TokenUsage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
  model: string | null = null;
  metadata: Record<string, unknown> = {};
  parentId: string | null = null;
  tags: string[] = [];

  constructor(opts: {
    name: string;
    callType: CallType;
    model?: string | null;
    parentId?: string | null;
    tags?: string[];
  }) {
    this.id = randomUUID().slice(0, 8);
    this.name = opts.name;
    this.callType = opts.callType;
    this.startedAt = new Date();
    this.model = opts.model ?? null;
    this.parentId = opts.parentId ?? null;
    this.tags = opts.tags ?? [];
  }

  finish(opts: {
    success?: boolean;
    error?: Error | string | null;
    tokenUsage?: Partial<TokenUsage>;
    model?: string | null;
    metadata?: Record<string, unknown>;
  } = {}): void {
    this.endedAt = new Date();
    this.latencyMs = this.endedAt.getTime() - this.startedAt.getTime();
    this.success = opts.success ?? true;

    if (opts.error) {
      const err = opts.error;
      this.error = err instanceof Error ? err.message : String(err);
      this.errorType = err instanceof Error ? err.constructor.name : "Error";
    }

    if (opts.tokenUsage) {
      this.tokenUsage = {
        promptTokens: opts.tokenUsage.promptTokens ?? 0,
        completionTokens: opts.tokenUsage.completionTokens ?? 0,
        totalTokens: opts.tokenUsage.totalTokens ?? 0,
      };
    }

    if (opts.model != null) this.model = opts.model;
    if (opts.metadata) Object.assign(this.metadata, opts.metadata);
  }

  toJSON(): ProfiledCallData {
    return {
      id: this.id,
      name: this.name,
      callType: this.callType,
      startedAt: this.startedAt.toISOString(),
      endedAt: this.endedAt?.toISOString() ?? null,
      latencyMs: this.latencyMs !== null ? Math.round(this.latencyMs * 1000) / 1000 : null,
      success: this.success,
      error: this.error,
      errorType: this.errorType,
      tokenUsage: this.tokenUsage,
      model: this.model,
      metadata: this.metadata,
      parentId: this.parentId,
      tags: this.tags,
    };
  }
}

// ─────────────────────────────────────────────────────────────
// Token extraction helpers
// ─────────────────────────────────────────────────────────────

function extractTokenUsageFromResponse(response: unknown): Partial<TokenUsage> | null {
  if (!response || typeof response !== "object") return null;
  const r = response as Record<string, unknown>;

  // OpenAI shape: response.usage.prompt_tokens / completion_tokens
  if (r["usage"] && typeof r["usage"] === "object") {
    const u = r["usage"] as Record<string, unknown>;
    if ("prompt_tokens" in u) {
      return {
        promptTokens: Number(u["prompt_tokens"]) || 0,
        completionTokens: Number(u["completion_tokens"]) || 0,
        totalTokens: Number(u["total_tokens"]) || 0,
      };
    }
    // Anthropic shape: response.usage.input_tokens / output_tokens
    if ("input_tokens" in u) {
      const prompt = Number(u["input_tokens"]) || 0;
      const completion = Number(u["output_tokens"]) || 0;
      return {
        promptTokens: prompt,
        completionTokens: completion,
        totalTokens: prompt + completion,
      };
    }
  }

  return null;
}

// ─────────────────────────────────────────────────────────────
// Profiler
// ─────────────────────────────────────────────────────────────

export class Profiler {
  readonly name: string;
  readonly tags: string[];
  private _calls: ProfiledCall[] = [];
  private _activeChain: string | null = null;
  private readonly _logger: AgentLensLogger;
  private readonly _metrics: MetricsCollector;
  private readonly _observability: ObservabilityConfig;

  constructor(name = "default", tags: string[] = [], observability: Partial<ObservabilityConfig> = {}) {
    this.name = name;
    this.tags = tags;
    this._observability = { ...defaultObservabilityConfig, ...observability };
    this._logger = new AgentLensLogger(this._observability);
    this._metrics = new MetricsCollector();
  }

  // ── Internal ──────────────────────────────────────────────

  private _startCall(
    name: string,
    callType: CallType,
    model?: string | null,
    tags?: string[],
  ): ProfiledCall {
    const call = new ProfiledCall({
      name,
      callType,
      model,
      parentId: this._activeChain,
      tags: [...this.tags, ...(tags ?? [])],
    });

    const payload = {
      callId: call.id,
      name: call.name,
      callType: call.callType,
      model: call.model,
      parentId: call.parentId,
    };

    if (callType === "chain") {
      this._logger.chainStarted(payload);
    } else {
      this._logger.callStarted(payload);
    }

    return call;
  }

  private _record(call: ProfiledCall): void {
    this._calls.push(call);

    if (this._observability.enableMetrics && call.latencyMs !== null) {
      this._metrics.record({
        success: call.success,
        latencyMs: call.latencyMs,
        tokenUsage: call.tokenUsage,
      });
    }

    const payload = {
      callId: call.id,
      name: call.name,
      callType: call.callType,
      model: call.model,
      parentId: call.parentId,
      success: call.success,
      latencyMs: call.latencyMs,
      errorType: call.errorType,
    };

    if (call.callType === "chain") {
      this._logger.chainCompleted(payload);
    } else if (call.success) {
      this._logger.callCompleted(payload);
    } else {
      this._logger.callFailed(payload);
    }

    this._logger.debugTrace({
      eventScope: "record",
      profiler: this.name,
      call: call.toJSON(),
      tokenBreakdown: call.tokenUsage,
    });
  }

  // ── Decorator-style wrappers ──────────────────────────────

  /**
   * Wrap a function as a profiled tool call.
   *
   * @example
   * const search = profiler.wrapTool("search_web", async (query: string) => { ... })
   */
  wrapTool<A extends unknown[], R>(
    name: string,
    fn: (...args: A) => R,
    opts: { tags?: string[] } = {},
  ): (...args: A) => R {
    const profiler = this;
    return function (this: unknown, ...args: A): R {
      const call = profiler._startCall(name, "tool", null, opts.tags);
      let result: R;
      try {
        result = fn.apply(this, args);
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        call.finish({ success: false, error });
        profiler._record(call);
        throw err;
      }

      if (result instanceof Promise) {
        return result.then(
          (v) => { call.finish({ success: true }); profiler._record(call); return v; },
          (err: Error) => { call.finish({ success: false, error: err }); profiler._record(call); throw err; },
        ) as unknown as R;
      }

      call.finish({ success: true });
      profiler._record(call);
      return result;
    };
  }

  /**
   * Wrap a function as a profiled LLM call.
   * Automatically extracts token usage from OpenAI/Anthropic response shapes.
   *
   * @example
   * const chat = profiler.wrapLLM("gpt-4o", (msgs) => openai.chat.completions.create(...))
   */
  wrapLLM<A extends unknown[], R>(
    model: string,
    fn: (...args: A) => R,
    opts: { name?: string; tags?: string[] } = {},
  ): (...args: A) => R {
    const callName = opts.name ?? `llm/${model}`;
    const profiler = this;

    return function (this: unknown, ...args: A): R {
      const call = profiler._startCall(callName, "llm", model, opts.tags);
      let result: R;
      try {
        result = fn.apply(this, args);
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        call.finish({ success: false, error });
        profiler._record(call);
        throw err;
      }

      if (result instanceof Promise) {
        return result.then(
          (response) => {
            const usage = extractTokenUsageFromResponse(response);
            const inferredModel =
              (response && typeof response === "object" && "model" in (response as object))
                ? String((response as Record<string, unknown>)["model"])
                : model;
            call.finish({ success: true, tokenUsage: usage ?? undefined, model: inferredModel });
            profiler._record(call);
            return response;
          },
          (err: Error) => {
            call.finish({ success: false, error: err });
            profiler._record(call);
            throw err;
          },
        ) as unknown as R;
      }

      const usage = extractTokenUsageFromResponse(result);
      call.finish({ success: true, tokenUsage: usage ?? undefined });
      profiler._record(call);
      return result;
    };
  }

  // ── Manual instrumentation ────────────────────────────────

  startCall(name: string, callType: CallType = "tool", model?: string): ProfiledCall {
    return this._startCall(name, callType, model);
  }

  endCall(
    call: ProfiledCall,
    opts: {
      success?: boolean;
      error?: Error | string | null;
      tokenUsage?: Partial<TokenUsage>;
      model?: string | null;
    } = {},
  ): void {
    call.finish(opts);
    this._record(call);
  }

  // ── Chain context ─────────────────────────────────────────

  async runChain<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const call = this._startCall(name, "chain");
    const previousChain = this._activeChain;
    this._activeChain = call.id;
    try {
      const result = await fn();
      call.finish({ success: true });
      return result;
    } catch (err) {
      call.finish({ success: false, error: err instanceof Error ? err : new Error(String(err)) });
      throw err;
    } finally {
      this._activeChain = previousChain;
      this._record(call);
    }
  }

  // ── Data access ───────────────────────────────────────────

  get calls(): ProfiledCall[] {
    return [...this._calls];
  }

  clear(): void {
    this._calls = [];
  }

  getCalls(opts: {
    callType?: CallType;
    successOnly?: boolean;
    failedOnly?: boolean;
  } = {}): ProfiledCall[] {
    let results = this.calls;
    if (opts.callType) results = results.filter((c) => c.callType === opts.callType);
    if (opts.successOnly) results = results.filter((c) => c.success);
    if (opts.failedOnly) results = results.filter((c) => !c.success);
    return results;
  }

  summary(): ProfilerSummary {
    const calls = this.calls;
    if (calls.length === 0) {
      return {
        profiler: this.name,
        totalCalls: 0,
        llmCalls: 0,
        toolCalls: 0,
        failedCalls: 0,
        successRate: 100,
        totalLatencyMs: 0,
        avgLatencyMs: 0,
        minLatencyMs: 0,
        maxLatencyMs: 0,
        tokenUsage: { promptTokens: 0, completionTokens: 0, totalTokens: 0 },
      };
    }

    const llmCalls = calls.filter((c) => c.callType === "llm");
    const toolCalls = calls.filter((c) => c.callType === "tool");
    const failed = calls.filter((c) => !c.success);
    const latencies = calls.map((c) => c.latencyMs ?? 0);
    const totalLatency = latencies.reduce((a, b) => a + b, 0);

    return {
      profiler: this.name,
      totalCalls: calls.length,
      llmCalls: llmCalls.length,
      toolCalls: toolCalls.length,
      failedCalls: failed.length,
      successRate: Math.round((1 - failed.length / calls.length) * 1000) / 10,
      totalLatencyMs: Math.round(totalLatency * 100) / 100,
      avgLatencyMs: Math.round((totalLatency / calls.length) * 100) / 100,
      minLatencyMs: Math.min(...latencies),
      maxLatencyMs: Math.max(...latencies),
      tokenUsage: {
        promptTokens: llmCalls.reduce((s, c) => s + c.tokenUsage.promptTokens, 0),
        completionTokens: llmCalls.reduce((s, c) => s + c.tokenUsage.completionTokens, 0),
        totalTokens: llmCalls.reduce((s, c) => s + c.tokenUsage.totalTokens, 0),
      },
    };
  }
}

// ─────────────────────────────────────────────────────────────
// Module-level default profiler
// ─────────────────────────────────────────────────────────────

export const defaultProfiler = new Profiler("global");

export function profileTool<A extends unknown[], R>(
  name: string,
  fn: (...args: A) => R,
): (...args: A) => R {
  return defaultProfiler.wrapTool(name, fn);
}

export function profileLLM<A extends unknown[], R>(
  model: string,
  fn: (...args: A) => R,
): (...args: A) => R {
  return defaultProfiler.wrapLLM(model, fn);
}
