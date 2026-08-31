import type { Edge, EdgeKind, GraphResponse, SymbolKind } from "../api/types"
import type { WorkspaceContext } from "../api/workspaces"

const NODE_KINDS: Record<string, SymbolKind> = {
  MODULE: "module",
  PACKAGE: "package",
  CLASS: "class",
  INTERFACE: "interface",
  FUNCTION: "function",
  METHOD: "method",
  CONST: "const",
  VARIABLE: "variable",
  ROUTE: "route",
}

const EDGE_KINDS: Record<string, EdgeKind> = {
  CALLS: "calls",
  REFERENCES: "references",
  CONTAINS: "contains",
  IMPLEMENTS: "implements",
  EXTENDS: "extends",
  HANDLES: "handles",
}

export function workspaceContextToGraph(context: WorkspaceContext): GraphResponse {
  const nodes = context.records.map((record) => ({
    id: record.source_identity,
    name: record.label,
    kind: NODE_KINDS[record.node_type.toUpperCase()] ?? "module",
    filePath: record.source_location,
    startLine: 0,
    endLine: 0,
  }))
  const known = new Set(nodes.map((node) => node.id))
  const edges: Edge[] = context.edges
    .filter((edge) => known.has(edge.source) && known.has(edge.target))
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      kind: EDGE_KINDS[edge.relation.toUpperCase()] ?? "references",
    }))
  return { nodes, edges }
}

export function citationRoute(citation: { source_location: string }, workspaceId: string): string | null {
  const location = citation.source_location.trim().split("#")[0].replace(/:L?\d+$/, "").trim()
  if (!location) return null
  if (location.includes("/") || location.includes(".")) return `/file/${location}`
  return `/graph?workspace=${encodeURIComponent(workspaceId)}&symbol=${encodeURIComponent(location)}`
}
