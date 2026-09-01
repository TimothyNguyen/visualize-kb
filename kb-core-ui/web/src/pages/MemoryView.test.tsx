// The chat memory section is the one surface where an archive delete is
// visible. A failed delete that renders identically to a success is the whole
// risk here, so these cover the error surface and the load state that would
// otherwise report an empty archive while the request is still in flight.

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, it, vi } from "vitest"

// The section debounces 300ms before it even asks, so the default 1s query
// window is thin once the whole suite is competing for one machine.
const WAIT = { timeout: 5000 }

vi.mock("./MemoryView.css", () => ({}))

const listWorkspaces = vi.fn()
const listChatMemories = vi.fn()
const searchChatMemories = vi.fn()
const deleteChatMemories = vi.fn()

vi.mock("../api/workspaces", async (original) => ({
  ...(await original<typeof import("../api/workspaces")>()),
  listWorkspaces: () => listWorkspaces(),
  listChatMemories: (workspaceId: string) => listChatMemories(workspaceId),
  searchChatMemories: (workspaceId: string, query: string, k: number) =>
    searchChatMemories(workspaceId, query, k),
  deleteChatMemories: (workspaceId: string, threadId?: string) =>
    deleteChatMemories(workspaceId, threadId),
}))

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  getMemory: () => Promise.resolve([]),
  searchMemory: () => Promise.resolve([]),
  addMemory: vi.fn(),
  deleteMemory: vi.fn(),
}))

const { MemoryView } = await import("./MemoryView")

function chatEntry() {
  return {
    id: "chat-alpha-turn-1",
    workspace_id: "alpha",
    thread_id: "t1",
    turn_id: "turn-1",
    seq: 1,
    title: "a question",
    text: "an answer",
    source: "chat://alpha/t1/turn-1",
    created_at: "2026-08-31T00:00:00Z",
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  listWorkspaces.mockResolvedValue([
    { id: "alpha", name: "Alpha", graph_name: "kb_workspace_alpha", status: "ready", sources: {}, runs: {} },
  ])
  listChatMemories.mockResolvedValue([chatEntry()])
  searchChatMemories.mockResolvedValue([])
  deleteChatMemories.mockResolvedValue({ workspace_id: "alpha", deleted: 1 })
})

it("says it is loading rather than reporting an empty archive", async () => {
  render(<MemoryView />)

  expect(await screen.findByText("Chat memory", {}, WAIT)).toBeInTheDocument()
  expect(screen.queryByText("No chat turns archived yet.")).not.toBeInTheDocument()
  expect(await screen.findByText("a question", {}, WAIT)).toBeInTheDocument()
})

it("shows why clearing a thread failed instead of looking like it worked", async () => {
  deleteChatMemories.mockRejectedValue(new Error("memory store is unavailable"))
  render(<MemoryView />)

  const clear = await screen.findByRole("button", { name: "Clear this thread" }, WAIT)
  await userEvent.click(clear)

  await waitFor(() => {
    expect(screen.getByText("memory store is unavailable")).toBeInTheDocument()
  }, WAIT)
})

it("shows why the archive could not be listed", async () => {
  listChatMemories.mockRejectedValue(new Error("workspace is gone"))
  render(<MemoryView />)

  expect(await screen.findByText("workspace is gone", {}, WAIT)).toBeInTheDocument()
})
