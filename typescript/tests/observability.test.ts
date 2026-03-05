import { AgentLensLogger, MetricsCollector } from "../src/observability";

describe("observability", () => {
  test("logger emits structured JSON", () => {
    const spy = jest.spyOn(console, "log").mockImplementation(() => undefined);
    const logger = new AgentLensLogger({ logLevel: "info", enableMetrics: true, debugMode: false });
    logger.callStarted({ name: "a", callId: "1" });

    expect(spy).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(String(spy.mock.calls[0][0])) as { event: string; name: string };
    expect(payload.event).toBe("call_started");
    expect(payload.name).toBe("a");
    spy.mockRestore();
  });

  test("metrics tracks counts and exports prometheus text", () => {
    const metrics = new MetricsCollector();
    metrics.record({
      success: true,
      latencyMs: 12,
      tokenUsage: { promptTokens: 2, completionTokens: 3, totalTokens: 5 },
    });
    metrics.record({ success: false, latencyMs: 7 });

    const snap = metrics.snapshot() as { callCount: number; errorCount: number };
    expect(snap.callCount).toBe(2);
    expect(snap.errorCount).toBe(1);

    const output = metrics.export();
    expect(output).toContain("agentlens_call_count_total 2");
    expect(output).toContain("agentlens_error_count_total 1");
  });
});
