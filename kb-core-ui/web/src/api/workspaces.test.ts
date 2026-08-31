import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiRequestError } from "./client"
import {
  addWorkspaceSource,
  createWorkspace,
  getWorkspaceContext,
  listWorkspaces,
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
