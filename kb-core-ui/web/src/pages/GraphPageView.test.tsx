import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { GraphResponse } from "../api/types"
import { GraphPageView } from "./GraphPageView"

const { getGraph, getGraphOverview, getSubgraph, search, getWorkspaceContext } = vi.hoisted(() => ({
  getGraph: vi.fn(),
  getGraphOverview: vi.fn(),
  getSubgraph: vi.fn(),
  search: vi.fn(),
  getWorkspaceContext: vi.fn(),
}))

vi.mock("../api/client", () => ({ getGraph, getGraphOverview, getSubgraph, search }))
vi.mock("../api/workspaces", () => ({ getWorkspaceContext }))

const overview: GraphResponse = {
  nodes: [{ id: "a", name: "a", kind: "function", filePath: "a.ts", startLine: 1, endLine: 1 }],
  edges: [],
}

const full: GraphResponse = {
  nodes: [
    { id: "a", name: "a", kind: "function", filePath: "a.ts", startLine: 1, endLine: 1 },
    { id: "b", name: "b", kind: "function", filePath: "b.ts", startLine: 1, endLine: 1 },
    { id: "c", name: "c", kind: "function", filePath: "c.ts", startLine: 1, endLine: 1 },
  ],
  edges: [
    { source: "a", target: "b", kind: "calls" },
    { source: "b", target: "c", kind: "calls" },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/graph"]}>
      <GraphPageView />
    </MemoryRouter>,
  )
}

describe("GraphPageView overview -> full graph load", () => {
  beforeEach(() => {
    getGraph.mockReset().mockResolvedValue(full)
    getGraphOverview.mockReset().mockResolvedValue(overview)
    getSubgraph.mockReset()
    search.mockReset().mockResolvedValue([])
    getWorkspaceContext.mockReset()
  })

  it("loads the overview graph first, without fetching the full graph", async () => {
    renderPage()

    expect(await screen.findByText("All (1)")).toBeInTheDocument()
    expect(getGraphOverview).toHaveBeenCalledTimes(1)
    expect(getGraph).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Load full graph" })).toBeInTheDocument()
  })

  it("swaps in the full graph on demand and hides the load button", async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText("All (1)")
    await user.click(screen.getByRole("button", { name: "Load full graph" }))

    expect(await screen.findByText("All (3)")).toBeInTheDocument()
    expect(getGraph).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: "Load full graph" })).not.toBeInTheDocument()
  })

  it("skips the overview and fetches a bounded subgraph when focused on a symbol", async () => {
    getSubgraph.mockResolvedValue({ ...full, nodes: full.nodes.slice(0, 2), edges: [full.edges[0]], center: "a" })

    render(
      <MemoryRouter initialEntries={["/graph?symbol=a&depth=2"]}>
        <GraphPageView />
      </MemoryRouter>,
    )

    expect(await screen.findByText("All (2)")).toBeInTheDocument()
    expect(getSubgraph).toHaveBeenCalledWith("a", 2)
    expect(getGraphOverview).not.toHaveBeenCalled()
    expect(getGraph).not.toHaveBeenCalled()
  })
})

describe("GraphPageView workspace mode", () => {
  const workspaceContext = {
    workspace_id: "alpha",
    source_ids: [],
    limit: 200,
    focus: "",
    records: [
      {
        source_identity: "src/a.py:Main",
        label: "Main",
        node_type: "CLASS",
        source_id: "repo",
        text: "",
        source_location: "src/a.py",
      },
    ],
    edges: [],
  }

  beforeEach(() => {
    getGraph.mockReset().mockResolvedValue(full)
    getGraphOverview.mockReset().mockResolvedValue(overview)
    getSubgraph.mockReset()
    search.mockReset().mockResolvedValue([])
    getWorkspaceContext.mockReset().mockResolvedValue(workspaceContext)
  })

  it("draws the workspace graph instead of the static export", async () => {
    render(
      <MemoryRouter initialEntries={["/graph?workspace=alpha"]}>
        <GraphPageView />
      </MemoryRouter>,
    )

    expect(await screen.findByText("All (1)")).toBeInTheDocument()
    expect(getWorkspaceContext).toHaveBeenCalledWith("alpha", { focus: "" })
    expect(getGraphOverview).not.toHaveBeenCalled()
  })

  it("asks for the bounded subgraph when a citation focuses a node", async () => {
    render(
      <MemoryRouter initialEntries={["/graph?workspace=alpha&symbol=src%2Fa.py%3AMain"]}>
        <GraphPageView />
      </MemoryRouter>,
    )

    await screen.findByText("All (1)")
    expect(getWorkspaceContext).toHaveBeenCalledWith("alpha", { focus: "src/a.py:Main" })
    expect(getSubgraph).not.toHaveBeenCalled()
  })

  it("reports a missing workspace instead of leaving a dead view", async () => {
    getWorkspaceContext.mockRejectedValue(new Error("workspace 'alpha' does not exist"))

    render(
      <MemoryRouter initialEntries={["/graph?workspace=alpha"]}>
        <GraphPageView />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/does not exist/)).toBeInTheDocument()
  })

  it("leaves the static graph path untouched when no workspace is selected", async () => {
    renderPage()

    await screen.findByText("All (1)")
    expect(getWorkspaceContext).not.toHaveBeenCalled()
    expect(getGraphOverview).toHaveBeenCalledTimes(1)
  })
})
