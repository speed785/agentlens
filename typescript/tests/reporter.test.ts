import * as fs from "fs";

import { Profiler } from "../src/profiler";
import { Reporter } from "../src/reporter";

function buildProfiler(): Profiler {
  const profiler = new Profiler("reporter");
  const llm = profiler.startCall("llm-step", "llm", "gpt-4o");
  profiler.endCall(llm, {
    success: true,
    tokenUsage: { promptTokens: 3, completionTokens: 2, totalTokens: 5 },
  });

  const tool = profiler.startCall("tool-step", "tool");
  profiler.endCall(tool, { success: false, error: new Error("bad") });
  return profiler;
}

describe("Reporter", () => {
  test("prints summary/table/timeline", () => {
    const reporter = new Reporter(buildProfiler());
    const spy = jest.spyOn(console, "log").mockImplementation(() => undefined);

    reporter.printSummary();
    reporter.printTable();
    reporter.printTimeline();

    const joined = spy.mock.calls.map((c) => String(c[0])).join("\n");
    expect(joined).toContain("AgentLens");
    expect(joined).toContain("Call Trace");
    expect(joined).toContain("Timeline");
    expect(joined).toContain("llm-step");

    spy.mockRestore();
  });

  test("toObject and exportJSON", () => {
    const reporter = new Reporter(buildProfiler());
    const tmpDir = fs.mkdtempSync("/tmp/agentlens-");
    const output = `${tmpDir}/trace.json`;
    const spy = jest.spyOn(console, "log").mockImplementation(() => undefined);

    reporter.exportJSON(output);
    const payload = JSON.parse(fs.readFileSync(output, "utf8"));

    expect(payload.profiler).toBe("reporter");
    expect(payload.summary.totalCalls).toBe(2);
    expect(payload.calls).toHaveLength(2);

    const objectPayload = reporter.toObject() as { summary: { failedCalls: number } };
    expect(objectPayload.summary.failedCalls).toBe(1);

    spy.mockRestore();
  });

  test("table can hide errors", () => {
    const reporter = new Reporter(buildProfiler());
    const spy = jest.spyOn(console, "log").mockImplementation(() => undefined);

    reporter.printTable({ showErrors: false });
    const joined = spy.mock.calls.map((c) => String(c[0])).join("\n");

    expect(joined).toContain("1 call(s) recorded");
    expect(joined).not.toContain("tool-step");

    spy.mockRestore();
  });
});
