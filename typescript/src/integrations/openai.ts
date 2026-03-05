/**
 * AgentLens — Drop-in wrapper for the OpenAI TypeScript SDK.
 *
 * @example
 * ```ts
 * import OpenAI from "openai";
 * import { Profiler } from "../profiler";
 * import { ProfiledOpenAI } from "./openai";
 *
 * const profiler = new Profiler("my-agent");
 * const openai = new ProfiledOpenAI(new OpenAI({ apiKey: "..." }), profiler);
 *
 * // Works exactly like the normal client
 * const res = await openai.chat.completions.create({
 *   model: "gpt-4o",
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
    if ("prompt_tokens" in u) {
      return {
        promptTokens: Number(u["prompt_tokens"]) || 0,
        completionTokens: Number(u["completion_tokens"]) || 0,
        totalTokens: Number(u["total_tokens"]) || 0,
      };
    }
  }
  return null;
}

class ProfiledChatCompletions {
  constructor(
    private readonly inner: { create: AnyFn },
    private readonly profiler: Profiler,
  ) {}

  async create(params: Record<string, unknown>, opts?: unknown): Promise<unknown> {
    const model = String(params["model"] ?? "unknown");
    const name = `openai.chat/${model}`;
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
}

class ProfiledChat {
  readonly completions: ProfiledChatCompletions;

  constructor(innerChat: { completions: { create: AnyFn } }, profiler: Profiler) {
    this.completions = new ProfiledChatCompletions(innerChat.completions, profiler);
  }
}

class ProfiledEmbeddings {
  constructor(
    private readonly inner: { create: AnyFn },
    private readonly profiler: Profiler,
  ) {}

  async create(params: Record<string, unknown>, opts?: unknown): Promise<unknown> {
    const model = String(params["model"] ?? "text-embedding-3-small");
    const name = `openai.embeddings/${model}`;
    const call = this.profiler.startCall(name, "llm", model);

    try {
      const response = await (this.inner.create as (p: unknown, o?: unknown) => Promise<unknown>)(
        params,
        opts,
      );
      const usage = extractUsage(response);
      this.profiler.endCall(call, { success: true, tokenUsage: usage ?? undefined });
      return response;
    } catch (err) {
      this.profiler.endCall(call, {
        success: false,
        error: err instanceof Error ? err : new Error(String(err)),
      });
      throw err;
    }
  }
}

/**
 * Drop-in wrapper for an `OpenAI` client instance.
 * All other attributes are forwarded transparently.
 */
export class ProfiledOpenAI {
  readonly chat: ProfiledChat;
  readonly embeddings: ProfiledEmbeddings;

  constructor(
    private readonly client: {
      chat: { completions: { create: AnyFn } };
      embeddings: { create: AnyFn };
      [key: string]: unknown;
    },
    public readonly profiler: Profiler = new Profiler("openai"),
  ) {
    this.chat = new ProfiledChat(client.chat, profiler);
    this.embeddings = new ProfiledEmbeddings(client.embeddings, profiler);
  }

  // Forward any other attributes to the underlying client
  [key: string]: unknown;
}
