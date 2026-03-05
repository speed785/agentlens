export interface ObservabilityConfig {
  logLevel: "debug" | "info" | "warn" | "error";
  enableMetrics: boolean;
  debugMode: boolean;
}

export const defaultObservabilityConfig: ObservabilityConfig = {
  logLevel: "info",
  enableMetrics: true,
  debugMode: false,
};

const severity: Record<ObservabilityConfig["logLevel"], number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

export class AgentLensLogger {
  constructor(public readonly config: ObservabilityConfig = defaultObservabilityConfig) {}

  private emit(level: ObservabilityConfig["logLevel"], event: string, payload: Record<string, unknown>): void {
    if (severity[level] < severity[this.config.logLevel]) return;
    const message = JSON.stringify({ event, timestampMs: Date.now(), ...payload });
    if (level === "error") {
      console.error(message);
      return;
    }
    console.log(message);
  }

  callStarted(payload: Record<string, unknown>): void {
    this.emit("info", "call_started", payload);
  }

  callCompleted(payload: Record<string, unknown>): void {
    this.emit("info", "call_completed", payload);
  }

  callFailed(payload: Record<string, unknown>): void {
    this.emit("error", "call_failed", payload);
  }

  chainStarted(payload: Record<string, unknown>): void {
    this.emit("info", "chain_started", payload);
  }

  chainCompleted(payload: Record<string, unknown>): void {
    this.emit("info", "chain_completed", payload);
  }

  debugTrace(payload: Record<string, unknown>): void {
    if (!this.config.debugMode) return;
    this.emit("debug", "debug_trace", payload);
  }
}

export class MetricsCollector {
  callCount = 0;
  errorCount = 0;
  totalLatencyMs = 0;
  tokenTotals = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
  private readonly buckets = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, Number.POSITIVE_INFINITY];
  private bucketCounts = new Map<number, number>();

  constructor() {
    this.reset();
  }

  reset(): void {
    this.callCount = 0;
    this.errorCount = 0;
    this.totalLatencyMs = 0;
    this.tokenTotals = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
    this.bucketCounts = new Map(this.buckets.map((b) => [b, 0]));
  }

  record(opts: { success: boolean; latencyMs: number; tokenUsage?: Partial<{ promptTokens: number; completionTokens: number; totalTokens: number }> }): void {
    this.callCount += 1;
    if (!opts.success) this.errorCount += 1;
    this.totalLatencyMs += opts.latencyMs;
    this.tokenTotals.promptTokens += opts.tokenUsage?.promptTokens ?? 0;
    this.tokenTotals.completionTokens += opts.tokenUsage?.completionTokens ?? 0;
    this.tokenTotals.totalTokens += opts.tokenUsage?.totalTokens ?? 0;

    for (const bucket of this.buckets) {
      if (opts.latencyMs <= bucket) {
        this.bucketCounts.set(bucket, (this.bucketCounts.get(bucket) ?? 0) + 1);
        break;
      }
    }
  }

  snapshot(): Record<string, unknown> {
    const latencyBuckets: Record<string, number> = {};
    for (const [bucket, count] of this.bucketCounts.entries()) {
      latencyBuckets[bucket === Number.POSITIVE_INFINITY ? "+Inf" : String(bucket)] = count;
    }

    return {
      callCount: this.callCount,
      errorCount: this.errorCount,
      totalLatencyMs: Math.round(this.totalLatencyMs * 1000) / 1000,
      tokenTotals: { ...this.tokenTotals },
      latencyBucketsMs: latencyBuckets,
    };
  }

  export(): string {
    const snap = this.snapshot() as {
      callCount: number;
      errorCount: number;
      totalLatencyMs: number;
      tokenTotals: { promptTokens: number; completionTokens: number; totalTokens: number };
      latencyBucketsMs: Record<string, number>;
    };

    const lines = [
      "# HELP agentlens_call_count_total Total number of profiled calls",
      "# TYPE agentlens_call_count_total counter",
      `agentlens_call_count_total ${snap.callCount}`,
      "# HELP agentlens_error_count_total Total number of failed profiled calls",
      "# TYPE agentlens_error_count_total counter",
      `agentlens_error_count_total ${snap.errorCount}`,
      "# HELP agentlens_latency_ms_sum Sum of call latency in milliseconds",
      "# TYPE agentlens_latency_ms_sum counter",
      `agentlens_latency_ms_sum ${snap.totalLatencyMs}`,
      "# HELP agentlens_tokens_total Total LLM token usage",
      "# TYPE agentlens_tokens_total counter",
      `agentlens_tokens_total{kind=\"prompt\"} ${snap.tokenTotals.promptTokens}`,
      `agentlens_tokens_total{kind=\"completion\"} ${snap.tokenTotals.completionTokens}`,
      `agentlens_tokens_total{kind=\"total\"} ${snap.tokenTotals.totalTokens}`,
      "# HELP agentlens_latency_ms_bucket Call latency histogram buckets",
      "# TYPE agentlens_latency_ms_bucket histogram",
    ];

    let cumulative = 0;
    for (const bucket of this.buckets) {
      const label = bucket === Number.POSITIVE_INFINITY ? "+Inf" : String(bucket);
      cumulative += snap.latencyBucketsMs[label] ?? 0;
      lines.push(`agentlens_latency_ms_bucket{le=\"${label}\"} ${cumulative}`);
    }

    lines.push(`agentlens_latency_ms_count ${snap.callCount}`);
    return lines.join("\n") + "\n";
  }
}
