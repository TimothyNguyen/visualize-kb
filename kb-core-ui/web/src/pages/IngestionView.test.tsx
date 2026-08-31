// The ingestion surface is the only place an operator sees why a source is
// smaller than the repo it came from, so these cover run state, the rejection
// report, and that polling stops rather than running forever.

import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("./IngestionView.css", () => ({}))

const listWorkspaces = vi.fn()
const getWorkspaceStats = vi.fn()
const addWorkspaceSource = vi.fn()
const startWorkspaceIngestion = vi.fn()
const refreshWorkspaceSource = vi.fn()
const removeWorkspaceSource = vi.fn()
const getIngestionRun = vi.fn()

vi.mock("../api/workspaces", async (original) => ({
  ...(await original<typeof import("../api/workspaces")>()),
  listWorkspaces: () => listWorkspaces(),
  getWorkspaceStats: (id: string) => getWorkspaceStats(id),
  createWorkspace: vi.fn(),
  addWorkspaceSource: (workspaceId: string, source: unknown) => addWorkspaceSource(workspaceId, source),
  startWorkspaceIngestion: (workspaceId: string, sourceId: string) =>
    startWorkspaceIngestion(workspaceId, sourceId),
  refreshWorkspaceSource: (workspaceId: string, sourceId: string) =>
    refreshWorkspaceSource(workspaceId, sourceId),
  removeWorkspaceSource: (workspaceId: string, sourceId: string) =>
    removeWorkspaceSource(workspaceId, sourceId),
  getIngestionRun: (workspaceId: string, runId: string) => getIngestionRun(workspaceId, runId),
}))

const { IngestionView } = await import("./IngestionView")

function workspace(sourceIds: string[] = ["repo"]) {
  return {
    id: "alpha",
    name: "Alpha",
    graph_name: "kb_workspace_alpha",
    status: "ready",
    sources: Object.fromEntries(
      sourceIds.map((id) => [
        id,
        { id, workspace_id: "alpha", kind: "local_repo", uri: "C:/src/repo", ref: "", status: "ready", active_version: "3" },
      ]),
    ),
    runs: {},
  }
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    workspace_id: "alpha",
    source_id: "repo",
    status: "succeeded",
    error: "",
    result: { reconcile_status: "published", counts: { nodes: 4, relationships: 3, chunks: 2, citations: 1 }, rejected: [] },
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  listWorkspaces.mockResolvedValue([workspace()])
  getWorkspaceStats.mockResolvedValue({ workspace_id: "alpha", nodes: 4, relationships: 3, source_ids: ["repo"] })
  startWorkspaceIngestion.mockResolvedValue(run())
  refreshWorkspaceSource.mockResolvedValue(run({ id: "run-2" }))
  removeWorkspaceSource.mockResolvedValue({ workspace_id: "alpha", source_id: "repo", deleted: true })
})

describe("IngestionView", () => {
  it("shows workspace graph stats for the selected workspace", async () => {
    render(<IngestionView />)

    expect(await screen.findByText("4")).toBeInTheDocument()
    expect(screen.getByText("relationships")).toBeInTheDocument()
  })

  it("reports run counts after an ingestion succeeds", async () => {
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Ingest" }))

    expect(await screen.findByText(/succeeded/i)).toBeInTheDocument()
    expect(screen.getByText(/4 nodes/)).toBeInTheDocument()
  })

  it("lists rejected records so a shrunken graph is explainable", async () => {
    startWorkspaceIngestion.mockResolvedValue(
      run({
        result: {
          reconcile_status: "published",
          counts: { nodes: 1, relationships: 0, chunks: 0, citations: 0 },
          rejected: [
            {
              record_type: "relationship",
              index: 2,
              record_id: "src/a.py:Ghost->src/b.py:Main",
              reason: "dangling endpoint",
            },
          ],
        },
      }),
    )
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Ingest" }))

    expect(await screen.findByText("src/a.py:Ghost->src/b.py:Main")).toBeInTheDocument()
    expect(screen.getByText("dangling endpoint")).toBeInTheDocument()
  })

  it("surfaces the failure reason when a run fails", async () => {
    startWorkspaceIngestion.mockResolvedValue(
      run({ status: "failed", error: "local repo source has no graph.json under C:/src/repo", result: {} }),
    )
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Ingest" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("no graph.json")
  })

  it("polls a still-running run until it reaches a terminal state, then stops", async () => {
    startWorkspaceIngestion.mockResolvedValue(run({ status: "running", result: {} }))
    getIngestionRun.mockResolvedValueOnce(run({ status: "running", result: {} })).mockResolvedValue(run())
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Ingest" }))

    await waitFor(() => expect(screen.getByText(/succeeded/i)).toBeInTheDocument())
    const polls = getIngestionRun.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(getIngestionRun.mock.calls.length).toBe(polls)
  })

  it("stops polling when the view unmounts mid-run", async () => {
    startWorkspaceIngestion.mockResolvedValue(run({ status: "running", result: {} }))
    getIngestionRun.mockResolvedValue(run({ status: "running", result: {} }))
    const view = render(<IngestionView />)
    await userEvent.click(await screen.findByRole("button", { name: "Ingest" }))
    await waitFor(() => expect(getIngestionRun).toHaveBeenCalled())

    view.unmount()
    const polls = getIngestionRun.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 150))

    expect(getIngestionRun.mock.calls.length).toBe(polls)
  })

  it("refreshes a source through the refresh route, not a fresh ingestion", async () => {
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Refresh" }))

    expect(refreshWorkspaceSource).toHaveBeenCalledWith("alpha", "repo")
    expect(startWorkspaceIngestion).not.toHaveBeenCalled()
  })

  it("removes a source and drops it from the list", async () => {
    // The server answers DELETE with a receipt, not a workspace, so the list
    // only shrinks if the view reloads it afterwards.
    listWorkspaces.mockResolvedValueOnce([workspace()]).mockResolvedValue([workspace([])])
    render(<IngestionView />)

    await userEvent.click(await screen.findByRole("button", { name: "Delete" }))

    await waitFor(() => expect(removeWorkspaceSource).toHaveBeenCalledWith("alpha", "repo"))
    await waitFor(() => expect(screen.queryByText("C:/src/repo")).toBeNull())
  })

  it("adds a local repo source through the form", async () => {
    addWorkspaceSource.mockResolvedValue({})
    render(<IngestionView />)
    await screen.findByLabelText("Source ID")

    await userEvent.type(screen.getByLabelText("Source ID"), "docs")
    await userEvent.selectOptions(screen.getByLabelText("Source kind"), "document_set")
    await userEvent.type(screen.getByLabelText("Source path"), "C:/docs")
    await userEvent.click(screen.getByRole("button", { name: "Add source" }))

    await waitFor(() =>
      expect(addWorkspaceSource).toHaveBeenCalledWith("alpha", { id: "docs", kind: "document_set", uri: "C:/docs" }),
    )
  })
})
