// Workspace graph records come from FalkorDB, the explorer was written for
// graph.json, and a citation has to land somewhere a reader can actually look.
// These cover that translation, including the cases with no valid target.

import { describe, expect, it } from "vitest"

import type { WorkspaceContext } from "../api/workspaces"
import { citationRoute, workspaceContextToGraph } from "./workspaceGraph"

function context(overrides: Partial<WorkspaceContext> = {}): WorkspaceContext {
  return {
    workspace_id: "alpha",
    source_ids: [],
    limit: 50,
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
      {
        source_identity: "src/b.py:helper",
        label: "helper",
        node_type: "ENTITY",
        source_id: "repo",
        text: "",
        source_location: "src/b.py",
      },
    ],
    edges: [{ source: "src/a.py:Main", target: "src/b.py:helper", relation: "CALLS", source_id: "repo" }],
    ...overrides,
  }
}

describe("workspaceContextToGraph", () => {
  it("maps records onto the explorer's symbol shape", () => {
    const { nodes } = workspaceContextToGraph(context())

    expect(nodes[0]).toEqual({
      id: "src/a.py:Main",
      name: "Main",
      kind: "class",
      filePath: "src/a.py",
      startLine: 0,
      endLine: 0,
    })
  })

  it("falls back to a renderable kind for graph node types the explorer has no colour for", () => {
    const { nodes } = workspaceContextToGraph(context())

    expect(nodes[1].kind).toBe("module")
  })

  it("maps relationship types onto edge kinds", () => {
    const { edges } = workspaceContextToGraph(context())

    expect(edges).toEqual([{ source: "src/a.py:Main", target: "src/b.py:helper", kind: "calls" }])
  })

  it("keeps an unknown relationship type visible instead of dropping the edge", () => {
    const { edges } = workspaceContextToGraph(
      context({
        edges: [{ source: "src/a.py:Main", target: "src/b.py:helper", relation: "MENTIONS", source_id: "repo" }],
      }),
    )

    expect(edges[0].kind).toBe("references")
  })

  it("drops edges whose endpoints fell outside the bounded record page", () => {
    // The node and edge queries are limited independently, so an edge can
    // point at a node that was never returned. Laying that out would throw.
    const { edges } = workspaceContextToGraph(
      context({
        edges: [{ source: "src/a.py:Main", target: "src/z.py:Missing", relation: "CALLS", source_id: "repo" }],
      }),
    )

    expect(edges).toEqual([])
  })
})

describe("citationRoute", () => {
  it("opens the file view when the citation points at a repo file", () => {
    expect(citationRoute({ source_location: "src/store.py" }, "alpha")).toBe("/file/src/store.py")
  })

  it("ignores a trailing line number and document fragment", () => {
    expect(citationRoute({ source_location: "docs/guide.md#chunk-2" }, "alpha")).toBe("/file/docs/guide.md")
    expect(citationRoute({ source_location: "src/store.py:42" }, "alpha")).toBe("/file/src/store.py")
  })

  it("falls back to the workspace graph when the location is a graph identity", () => {
    expect(citationRoute({ source_location: "Store" }, "alpha")).toBe("/graph?workspace=alpha&symbol=Store")
  })

  it("returns nothing when there is no target, so the caller can say so", () => {
    expect(citationRoute({ source_location: "" }, "alpha")).toBeNull()
    expect(citationRoute({ source_location: "   " }, "alpha")).toBeNull()
  })
})
