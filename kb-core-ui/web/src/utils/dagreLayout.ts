import dagre from "@dagrejs/dagre"
import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react"

const NODE_WIDTH = 200
const NODE_HEIGHT = 46

export function layoutWithDagre<N extends RFNode, E extends RFEdge>(
  nodes: N[],
  edges: E[],
  direction: "LR" | "TB" = "LR",
): N[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: direction, nodesep: 32, ranksep: 90, marginx: 24, marginy: 24 })

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })
}

export { NODE_WIDTH, NODE_HEIGHT }
