/**
 * AgentLens — Drop-in wrapper for the Anthropic TypeScript SDK.
 *
 * @example
 * ```ts
 * import Anthropic from "@anthropic-ai/sdk";
 * import { Profiler } from "../profiler";
 * import { ProfiledAnthropic } from "./anthropic";
 *
 * const profiler = new Profiler("my-agent");
 * const client = new ProfiledAnthropic(new Anthropic({ apiKey: "..." }), profiler);
 *
 * const message = await client.messages.create({
 *   model: "claude-opus-4-5",
 *   max_tokens: 1024,
 *   messages: [{ role: "user", content: "Hello!" }],
 * });
 * ```
 */

import { Profiler, TokenUsage } from "../profiler";

type AnyFn = (...args: unknown[]) => unknown;

function extractUsage(response: unknown): Partial<TokenUsage> | null {
  if (!response || typeof response !== "object") return null;
  const r = response as Record<string, unknown>;
  if (r["usage"] && typeof r["usage"] === "object") {
    const u = r["usage"] as Record<string, unknown>;
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

class ProfiledMessages {
  constructor(
    private readonly inner: { create: AnyFn; stream?: AnyFn },
    private readonly profiler: Profiler,
  ) {}

  async create(params: Record<string, unknown>, opts?: unknown): Promise<unknown> {
    const model = String(params["model"] ?? "unknown");
    const name = `anthropic.messages/${model}`;
    const call = this.profiler.startCall(name, "llm", model);

    try {
      const response = await (this.inner.create as (p: unknown, o?: unknown) => Promise<unknown>)(
        params,
        opts,
      );
      const usage = extractUsage(response);
      const inferredModel =
        response && typeof response === "object" && "model" in (response as object)
          ? String((response as Record<string, unknown>)["model"])
          : model;
      this.profiler.endCall(call, {
        success: true,
        tokenUsage: usage ?? undefined,
        model: inferredModel,
      });
      return response;
    } catch (err) {
      this.profiler.endCall(call, {
        success: false,
        error: err instanceof Error ? err : new Error(String(err)),
      });
      throw err;
    }
  }

  /**
   * Wraps the streaming `client.messages.stream(...)` helper.
   */
  stream(params: Record<string, unknown>): unknown {
    const model = String(params["model"] ?? "unknown");
    const name = `anthropic.messages.stream/${model}`;
    const call = this.profiler.startCall(name, "llm", model);
    const profiler = this.profiler;

    if (!this.inner.stream) {
      throw new Error("Underlying Anthropic client does not support .stream()");
    }

    const streamCtx = (this.inner.stream as (p: unknown) => unknown)(params);

    // Wrap in a proxy that records the call when the stream finalizes
    return new Proxy(streamCtx as object, {
      get(target, prop) {
        const value = Reflect.get(target, prop);
        if (prop === "finalMessage" && typeof value === "function") {
          return async function (this: unknown, ...args: unknown[]) {
            try {
              const result = await (value as AnyFn).apply(target, args);
              const usage = extractUsage(result);
              profiler.endCall(call, { success: true, tokenUsage: usage ?? undefined });
              return result;
            } catch (err) {
              profiler.endCall(call, {
                success: false,
                error: err instanceof Error ? err : new Error(String(err)),
              });
              throw err;
            }
          };
        }
        if (typeof value === "function") {
          return value.bind(target);
        }
        return value;
      },
    });
  }
}

/**
 * Drop-in wrapper for an `Anthropic` client instance.
 */
export class ProfiledAnthropic {
  readonly messages: ProfiledMessages;

  constructor(
    private readonly client: {
      messages: { create: AnyFn; stream?: AnyFn };
      [key: string]: unknown;
    },
    public readonly profiler: Profiler = new Profiler("anthropic"),
  ) {
    this.messages = new ProfiledMessages(client.messages, profiler);
  }

  [key: string]: unknown;
}
