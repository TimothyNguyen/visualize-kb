// Reads the same frozen files that the Python side regenerates and
// byte-compares in tests/test_rag_chat_contract_fixtures.py. If a wire field
// or SSE frame changes, both suites fail together instead of drifting apart.

import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it, vi, afterEach } from "vitest"

import { ApiRequestError } from "./client"
import {
  askChat,
  cancelChat,
  chatStreamUrl,
  createChatStreamParser,
  getChatThread,
  streamChat,
} from "./chat"
import type { ChatAnswer, ChatStreamEvent, ChatThread } from "./types"

// Read off disk rather than imported, so Vite never rewrites, bundles or
// otherwise reformats a byte of the frozen contract on its way into a test.
const CONTRACT_DIR = resolve(process.cwd(), "..", "contracts", "rag-chat", "v1")

function fixture(name: string): string {
  return readFileSync(resolve(CONTRACT_DIR, name), "utf-8")
}

function parseAll(text: string, chunkSize = text.length): ChatStreamEvent[] {
  const parse = createChatStreamParser()
  const events: ChatStreamEvent[] = []
  for (let at = 0; at < text.length; at += chunkSize) {
    events.push(...parse(text.slice(at, at + chunkSize)))
  }
  return events
}

function mockFetch(body: string, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status < 400,
      status,
      statusText: "",
      json: async () => JSON.parse(body),
      body: {
        getReader() {
          let sent = false
          return {
            async read() {
              if (sent) return { done: true, value: undefined }
              sent = true
              return { done: false, value: new TextEncoder().encode(body) }
            },
            releaseLock() {},
          }
        },
      },
    })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("createChatStreamParser", () => {
  it("yields queued, tokens and exactly one terminal event", () => {
    const events = parseAll(fixture("chat_stream.sse"))
    const names = events.map((event) => event.event)

    expect(names[0]).toBe("queued")
    expect(names.filter((name) => name === "token").length).toBeGreaterThan(0)
    expect(names.at(-1)).toBe("completed")
    expect(names.filter((name) => ["completed", "cancelled", "error"].includes(name))).toHaveLength(1)
  })

  it("drops heartbeat comments instead of surfacing them as content", () => {
    const text = fixture("chat_stream.sse")

    expect(text).toContain(": heartbeat\n\n")
    expect(parseAll(text).map((event) => event.event)).not.toContain("heartbeat")
  })

  it("reassembles frames split across chunk boundaries", () => {
    const text = fixture("chat_stream.sse")

    expect(parseAll(text, 7)).toEqual(parseAll(text))
  })

  it("carries the completed payload verbatim from the frozen answer", () => {
    const completed = parseAll(fixture("chat_stream.sse")).at(-1)!
    const frozen = JSON.parse(fixture("chat_complete.json")) as ChatAnswer

    expect(completed.event).toBe("completed")
    const answer = completed.data as ChatAnswer
    expect(answer.answer).toBe(frozen.answer)
    expect(answer.citations).toEqual(frozen.citations)
    expect(answer.context).toEqual(frozen.context)
    expect(answer.explain_graph).toEqual(frozen.explain_graph)
    expect(answer.source_map).toEqual(frozen.source_map)
    expect(answer.strategy).toBe(frozen.strategy)
    expect(answer.degraded).toBe(frozen.degraded)
    expect(answer.error).toBe("")
  })

  it("ends a cancelled stream on cancelled, never on completed", () => {
    const names = parseAll(fixture("chat_stream_cancelled.sse")).map((event) => event.event)

    expect(names).toEqual(["queued", "cancelled"])
  })

  it("ends a failed stream on one error event carrying status and message", () => {
    const events = parseAll(fixture("chat_stream_error.sse"))
    const last = events.at(-1)!

    expect(last.event).toBe("error")
    expect(last.data).toMatchObject({ status: 503 })
    expect((last.data as { message: string }).message).not.toContain("falkor://")
  })
})

describe("streamChat", () => {
  it("resolves with the terminal event after replaying every frame", async () => {
    mockFetch(fixture("chat_stream.sse"))
    const seen: string[] = []

    const terminal = await streamChat("alpha", { query: "graph records" }, (event) => seen.push(event.event))

    expect(terminal!.event).toBe("completed")
    expect(seen).not.toContain("heartbeat")
    expect(seen.at(-1)).toBe("completed")
  })
})

describe("chatStreamUrl", () => {
  it("passes scope and tuning through as the server's own query names", () => {
    const url = chatStreamUrl("alpha", {
      query: "graph records",
      thread_id: "thread-fixture",
      query_id: "q-fixture-1",
      strategy: "local",
      requested_k: 5,
      allowed_source_ids: ["repo", "docs"],
    })
    const params = new URLSearchParams(url.split("?")[1])

    expect(url.startsWith("/api/rag/workspaces/alpha/chat/stream?")).toBe(true)
    expect(params.get("query")).toBe("graph records")
    expect(params.get("thread_id")).toBe("thread-fixture")
    expect(params.get("query_id")).toBe("q-fixture-1")
    expect(params.get("strategy")).toBe("local")
    expect(params.get("requested_k")).toBe("5")
    expect(params.getAll("allowed_source_ids")).toEqual(["repo", "docs"])
  })
})

describe("chat requests", () => {
  it("returns the frozen answer shape from a complete chat", async () => {
    mockFetch(fixture("chat_complete.json"))

    const answer = await askChat("alpha", { query: "graph records" })

    expect(answer).toEqual(JSON.parse(fixture("chat_complete.json")))
  })

  it("replays a persisted turn under the same answer type as a live one", async () => {
    mockFetch(fixture("chat_thread.json"))

    const thread: ChatThread = await getChatThread("alpha", "thread-fixture")
    const replayed = thread.turns[0].response

    expect(thread.workspace_id).toBe("alpha")
    expect(thread.turns[0].seq).toBe(1)
    // Key order is not part of the contract; the field set is.
    expect(Object.keys(replayed).sort()).toEqual(Object.keys(JSON.parse(fixture("chat_complete.json"))).sort())
  })

  it.each(JSON.parse(fixture("errors.json")) as { case: string; status: number; body: { error: string } }[])(
    "surfaces the server's $status message for $case",
    async ({ status, body }) => {
      mockFetch(JSON.stringify(body), status)

      const failure = await cancelChat("alpha", "q-fixture-1").catch((error: unknown) => error)

      expect(failure).toBeInstanceOf(ApiRequestError)
      expect((failure as ApiRequestError).status).toBe(status)
      expect((failure as ApiRequestError).message).toBe(body.error)
      expect((failure as ApiRequestError).message).not.toContain("falkor://")
    },
  )
})
