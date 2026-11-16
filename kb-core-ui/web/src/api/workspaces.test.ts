import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiRequestError } from "./client"
import {
  addWorkspaceSource,
  createWorkspace,
  deleteChatMemories,
  getWorkspaceContext,
  listChatMemories,
  listWorkspaces,
  searchChatMemories,
  startWorkspaceIngestion,
} from "./workspaces"

afterEach(() => vi.unstubAllGlobals())

function mockResponse(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status < 400,
      status,
      statusText: "",
      json: async () => body,
    })),
  )
}

describe("workspace API", () => {
  it("uses backend-owned workspace routes", async () => {
    mockResponse([])

    await listWorkspaces()

    expect(fetch).toHaveBeenCalledWith("/api/rag/workspaces", undefined)
  })

  it("encodes workspace and source identifiers", async () => {
    mockResponse({ status: "succeeded" })

    await startWorkspaceIngestion("repo one", "docs/api")

    expect(fetch).toHaveBeenCalledWith(
      "/api/rag/workspaces/repo%20one/sources/docs%2Fapi/ingestions",
      expect.objectContaining({ method: "POST" }),
    )
  })

  it("sends only source metadata, never graph credentials", async () => {
    mockResponse({ id: "repo" }, 201)

    await addWorkspaceSource("internal", { id: "repo", kind: "local_repo", uri: "C:/src/repo" })

    const request = vi.mocked(fetch).mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(request.body))).toEqual({
      id: "repo",
      kind: "local_repo",
      uri: "C:/src/repo",
      ref: "",
    })
  })

  it("asks for graph context through the backend, with the focus escaped", async () => {
    mockResponse({ records: [], edges: [] })

    await getWorkspaceContext("alpha", { focus: "src/a.py:Main", sourceIds: ["repo"], limit: 20 })

    expect(fetch).toHaveBeenCalledWith(
      "/api/rag/workspaces/alpha/context?limit=20&source=repo&focus=src%2Fa.py%3AMain",
      undefined,
    )
  })

  it("surfaces server validation messages", async () => {
    mockResponse({ error: "workspace id is invalid" }, 400)

    const error = await createWorkspace("Bad", "Bad").catch((failure: unknown) => failure)

    expect(error).toBeInstanceOf(ApiRequestError)
    expect((error as Error).message).toBe("workspace id is invalid")
  })
})

describe("chat memory", () => {
  it("lists a workspace without a thread filter", async () => {
    mockResponse({ workspace_id: "alpha", entries: [] })

    await listChatMemories("alpha")

    expect(fetch).toHaveBeenCalledWith("/api/rag/workspaces/alpha/memory", undefined)
  })

  it("lists one thread", async () => {
    mockResponse({ workspace_id: "alpha", entries: [] })

    await listChatMemories("alpha", "t 1")

    expect(fetch).toHaveBeenCalledWith("/api/rag/workspaces/alpha/memory?thread=t+1", undefined)
  })

  it("escapes the search query and passes top", async () => {
    mockResponse({ workspace_id: "alpha", hits: [] })

    await searchChatMemories("alpha", "graph records", 10)

    expect(fetch).toHaveBeenCalledWith(
      "/api/rag/workspaces/alpha/memory/search?q=graph+records&top=10",
      undefined,
    )
  })

  it("returns the hits", async () => {
    mockResponse({
      workspace_id: "alpha",
      hits: [{ entry: { id: "m1", title: "q" }, score: 0.5 }],
    })

    const hits = await searchChatMemories("alpha", "q")

    expect(hits).toHaveLength(1)
    expect(hits[0].score).toBe(0.5)
  })

  it("deletes a thread and returns the count", async () => {
    mockResponse({ workspace_id: "alpha", deleted: 2 })

    const deleted = await deleteChatMemories("alpha", "t1")

    expect(fetch).toHaveBeenCalledWith(
      "/api/rag/workspaces/alpha/memory?thread=t1",
      expect.objectContaining({ method: "DELETE" }),
    )
    expect(deleted).toBe(2)
  })
})
