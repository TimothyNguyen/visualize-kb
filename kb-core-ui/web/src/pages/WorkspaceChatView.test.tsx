// CopilotKit renders the transcript; this suite covers what the app itself
// owns -- which workspace, strategy and sources reach the agent's state, since
// that state is the authorization scope the server enforces every turn.

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const setState = vi.fn()
const agent = { state: {} as Record<string, unknown> }

vi.mock("@copilotkit/react-core/v2", () => ({
  CopilotKit: ({ children }: { children: React.ReactNode }) => <div data-testid="copilotkit">{children}</div>,
  CopilotChat: ({ agentId }: { agentId: string }) => <div data-testid="chat">{agentId}</div>,
  UseAgentUpdate: { OnStateChanged: "OnStateChanged" },
  useAgent: () => ({ agent: { ...agent, setState }, isReady: true }),
}))
vi.mock("@copilotkit/react-core/v2/styles.css", () => ({}))
vi.mock("./WorkspaceChatView.css", () => ({}))

const listWorkspaces = vi.fn()
const getWorkspaceStats = vi.fn()
const startWorkspaceIngestion = vi.fn()

vi.mock("../api/workspaces", () => ({
  listWorkspaces: () => listWorkspaces(),
  getWorkspaceStats: (id: string) => getWorkspaceStats(id),
  startWorkspaceIngestion: (workspaceId: string, sourceId: string) =>
    startWorkspaceIngestion(workspaceId, sourceId),
  createWorkspace: vi.fn(),
  addWorkspaceSource: vi.fn(),
}))

const { WorkspaceChatView } = await import("./WorkspaceChatView")

function workspace(id: string, name: string, sourceIds: string[]) {
  return {
    id,
    name,
    graph_name: `kb_workspace_${id}`,
    status: "ready",
    sources: Object.fromEntries(
      sourceIds.map((sourceId) => [
        sourceId,
        { id: sourceId, workspace_id: id, kind: "local_repo", uri: "", ref: "", status: "ready", active_version: "1" },
      ]),
    ),
    runs: {},
  }
}

function lastState(): Record<string, unknown> {
  return setState.mock.calls.at(-1)![0]
}

beforeEach(() => {
  vi.clearAllMocks()
  agent.state = {}
  listWorkspaces.mockResolvedValue([workspace("alpha", "Alpha", ["repo", "docs"]), workspace("beta", "Beta", ["wiki"])])
  getWorkspaceStats.mockResolvedValue({ workspace_id: "alpha", nodes: 12, relationships: 7, source_ids: ["repo"] })
})

describe("WorkspaceChatView", () => {
  it("scopes the agent to the first workspace once workspaces load", async () => {
    render(<WorkspaceChatView />)

    await waitFor(() => expect(setState).toHaveBeenCalled())
    expect(lastState()).toMatchObject({ workspace_id: "alpha", strategy: "auto" })
    expect(await screen.findByTestId("chat")).toHaveTextContent("kb-core")
  })

  it("re-scopes the agent when the workspace is switched", async () => {
    render(<WorkspaceChatView />)
    await screen.findByRole("option", { name: "Beta" })

    await userEvent.selectOptions(screen.getByLabelText("Workspace"), "beta")

    await waitFor(() => expect(lastState().workspace_id).toBe("beta"))
    expect(lastState().allowed_source_ids).toEqual(["wiki"])
  })

  it("sends the selected retrieval strategy to the agent", async () => {
    render(<WorkspaceChatView />)
    await waitFor(() => expect(setState).toHaveBeenCalled())

    await userEvent.selectOptions(screen.getByLabelText(/Retrieval/), "multi_path")

    await waitFor(() => expect(lastState().strategy).toBe("multi_path"))
  })

  it("narrows retrieval scope when a source is unchecked", async () => {
    render(<WorkspaceChatView />)
    await screen.findByRole("checkbox", { name: "repo" })

    await userEvent.click(screen.getByRole("checkbox", { name: "repo" }))

    await waitFor(() => expect(lastState().allowed_source_ids).not.toContain("repo"))
  })

  it("renders citations from the answer the agent last streamed back", async () => {
    agent.state = {
      last_answer: {
        citations: [{ evidence_id: "node-repo", source_id: "repo", source_location: "repo.py:L1", origin: "retrieval" }],
        insufficient_evidence: false,
      },
    }

    render(<WorkspaceChatView />)

    expect(await screen.findByText("1 citations")).toBeInTheDocument()
    expect(screen.getByText("repo.py:L1")).toBeInTheDocument()
  })

  it("flags a degraded answer that found no supporting evidence", async () => {
    agent.state = { last_answer: { citations: [], insufficient_evidence: true } }

    render(<WorkspaceChatView />)

    expect(await screen.findByText("Insufficient evidence")).toBeInTheDocument()
  })

  it("surfaces a failed workspace load without rendering chat", async () => {
    listWorkspaces.mockRejectedValue(new Error("workspace backend unavailable"))

    render(<WorkspaceChatView />)

    expect(await screen.findByRole("alert")).toHaveTextContent("workspace backend unavailable")
    expect(screen.queryByTestId("chat")).toBeNull()
  })

  it("reports ingestion failures instead of leaving the button stuck", async () => {
    startWorkspaceIngestion.mockRejectedValue(new Error("ingestion refused"))
    render(<WorkspaceChatView />)

    await userEvent.click((await screen.findAllByRole("button", { name: "Ingest" }))[0])

    expect(await screen.findByRole("alert")).toHaveTextContent("ingestion refused")
    expect(screen.getAllByRole("button", { name: "Ingest" })[0]).toBeEnabled()
  })
})
