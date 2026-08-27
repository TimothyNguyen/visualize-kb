import { useMemo, useState } from "react"
import { Background, Controls, MiniMap, ReactFlow, type Edge as RFEdge, type NodeTypes } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import type { Edge, SymbolKind, SymbolRef } from "../../api/types"
import { layoutWithDagre } from "../../utils/dagreLayout"
import { edgeColor, kindHexColor } from "../../utils/style"
import { SymbolNode, type SymbolFlowNode, type SymbolNodeData } from "../SymbolGraph/SymbolNode"
import { GraphLegend } from "./GraphLegend"
import "./GlobalGraph.css"

const nodeTypes: NodeTypes = { symbol: SymbolNode }

function dirOf(path: string): string {
  const i = path.lastIndexOf("/")
  return i >= 0 ? path.slice(0, i) : "(root)"
}

export function GlobalGraph({
  nodes: symbolNodes,
  edges: symbolEdges,
  centerId,
}: {
  nodes: SymbolRef[]
  edges: Edge[]
  centerId?: string
}) {
  const [scope, setScope] = useState("")

  // Entry points (nothing calls them) are where a reader should start —
  // route/CLI/page handlers live here. Leaves (call nothing themselves)
  // are the opposite end: pure helpers and side dependencies. Computed
  // from the full edge set, independent of the scope filter below, since
  // "is this a starting position" is a property of the whole repo.
  const roleById = useMemo(() => {
    const hasIncomingCall = new Set<string>()
    const hasOutgoingCall = new Set<string>()
    for (const e of symbolEdges) {
      if (e.kind !== "calls") continue
      hasOutgoingCall.add(e.source)
      hasIncomingCall.add(e.target)
    }
    const roles = new Map<string, SymbolNodeData["role"]>()
    for (const n of symbolNodes) {
      if (!hasIncomingCall.has(n.id) && hasOutgoingCall.has(n.id)) roles.set(n.id, "entry")
      else if (!hasOutgoingCall.has(n.id) && hasIncomingCall.has(n.id)) roles.set(n.id, "leaf")
      else roles.set(n.id, "normal")
    }
    return roles
  }, [symbolNodes, symbolEdges])

  const scopes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const n of symbolNodes) {
      const d = dirOf(n.filePath)
      counts.set(d, (counts.get(d) ?? 0) + 1)
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [symbolNodes])

  // Scoping to one directory answers "show me this page/module on its
  // own" — the ask for page-by-page separation — while still pulling in
  // directly-connected nodes from elsewhere (dimmed) so real cross-module
  // dependencies stay visible instead of silently vanishing.
  const { visibleNodes, visibleEdges, coreIds } = useMemo(() => {
    if (!scope) return { visibleNodes: symbolNodes, visibleEdges: symbolEdges, coreIds: null as Set<string> | null }
    const core = new Set(symbolNodes.filter((n) => dirOf(n.filePath) === scope).map((n) => n.id))
    const included = new Set(core)
    for (const e of symbolEdges) {
      if (core.has(e.source)) included.add(e.target)
      if (core.has(e.target)) included.add(e.source)
    }
    return {
      visibleNodes: symbolNodes.filter((n) => included.has(n.id)),
      visibleEdges: symbolEdges.filter((e) => included.has(e.source) && included.has(e.target)),
      coreIds: core,
    }
  }, [scope, symbolNodes, symbolEdges])

  const { nodes, edges } = useMemo(() => {
    const rawNodes: SymbolFlowNode[] = visibleNodes.map((s) => ({
      id: s.id,
      type: "symbol",
      position: { x: 0, y: 0 },
      data: {
        label: s.name,
        kind: s.kind,
        filePath: s.filePath,
        isCenter: s.id === centerId,
        role: roleById.get(s.id) ?? "normal",
        dimmed: coreIds !== null && !coreIds.has(s.id),
      },
    }))
    const rfEdges: RFEdge[] = visibleEdges.map((e, i) => ({
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: e.kind,
      style: { stroke: edgeColor(e.kind) },
      markerEnd: { type: "arrowclosed" as const, color: edgeColor(e.kind) },
    }))
    const laidOut = layoutWithDagre(rawNodes, rfEdges, "LR")
    return { nodes: laidOut, edges: rfEdges }
  }, [visibleNodes, visibleEdges, centerId, roleById, coreIds])

  return (
    <div className="global-graph">
      <div className="global-graph-scope">
        <label>
          Scope
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">All ({symbolNodes.length})</option>
            {scopes.map(([dir, count]) => (
              <option key={dir} value={dir}>
                {dir} ({count})
              </option>
            ))}
          </select>
        </label>
        {scope && <span className="global-graph-scope-hint">dimmed nodes are outside this scope, shown for context</span>}
      </div>
      <ReactFlow
        // React Flow's `fitView` prop only fits the viewport once, on
        // mount — it doesn't re-run when the node set changes size or
        // position. Remounting on scope/focus changes forces a fresh fit;
        // without this, switching scope leaves the camera pointed at
        // wherever the *previous* (often much larger) graph was.
        key={`${scope}:${centerId ?? "all"}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={2}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => {
            const data = n.data as { kind?: SymbolKind } | undefined
            return data?.kind ? kindHexColor(data.kind) : "#888"
          }}
        />
      </ReactFlow>
      <GraphLegend />
    </div>
  )
}
