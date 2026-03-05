import { Profiler } from "../src/profiler";

describe("Profiler", () => {
  test("wrapTool records success and errors", async () => {
    const profiler = new Profiler("unit", ["suite"]);

    const ok = profiler.wrapTool("ok-tool", (x: number) => x * 2, { tags: ["math"] });
    const bad = profiler.wrapTool("bad-tool", () => {
      throw new Error("boom");
    });

    expect(ok(2)).toBe(4);
    expect(() => bad()).toThrow("boom");

    const calls = profiler.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0].name).toBe("ok-tool");
    expect(calls[0].tags).toEqual(expect.arrayContaining(["suite", "math"]));
    expect(calls[1].success).toBe(false);
    expect(calls[1].errorType).toBe("Error");
  });

  test("wrapLLM extracts OpenAI and Anthropic token usage", async () => {
    const profiler = new Profiler("tokens");
    const openai = profiler.wrapLLM("gpt-4o", async () => ({
      model: "gpt-4o-mini",
      usage: { prompt_tokens: 5, completion_tokens: 4, total_tokens: 9 },
    }));

    const anthropic = profiler.wrapLLM("claude", async () => ({
      usage: { input_tokens: 7, output_tokens: 3 },
    }));

    await openai();
    await anthropic();

    const [first, second] = profiler.calls;
    expect(first.tokenUsage.totalTokens).toBe(9);
    expect(first.model).toBe("gpt-4o-mini");
    expect(second.tokenUsage.promptTokens).toBe(7);
    expect(second.tokenUsage.completionTokens).toBe(3);
    expect(second.tokenUsage.totalTokens).toBe(10);
  });

  test("manual instrumentation, chains, and filters", async () => {
    const profiler = new Profiler("manual");

    const manual = profiler.startCall("manual", "llm", "gpt-4o");
    profiler.endCall(manual, { success: true, tokenUsage: { promptTokens: 1, completionTokens: 2, totalTokens: 3 } });

    await profiler.runChain("pipeline", async () => {
      const nested = profiler.wrapTool("nested", () => "ok");
      return nested();
    });

    await expect(
      profiler.runChain("broken", async () => {
        throw new Error("fail");
      }),
    ).rejects.toThrow("fail");

    expect(profiler.getCalls({ callType: "llm" }).length).toBeGreaterThanOrEqual(1);
    expect(profiler.getCalls({ failedOnly: true }).length).toBe(1);

    const summary = profiler.summary();
    expect(summary.totalCalls).toBe(4);
    expect(summary.failedCalls).toBe(1);
    expect(summary.tokenUsage.totalTokens).toBe(3);
  });

  test("async wrapper errors are tracked", async () => {
    const profiler = new Profiler("async");

    const asyncTool = profiler.wrapTool("async-tool", async () => {
      throw new Error("oops");
    });

    await expect(asyncTool()).rejects.toThrow("oops");
    expect(profiler.calls[0].success).toBe(false);
    expect(profiler.calls[0].error).toBe("oops");
  });
});
