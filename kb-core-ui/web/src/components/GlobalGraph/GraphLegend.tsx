import { EDGE_LABEL, edgeColor } from "../../utils/style"
import type { EdgeKind } from "../../api/types"
import "./GraphLegend.css"

const EDGE_KINDS: EdgeKind[] = ["calls", "references", "contains", "implements", "extends", "handles"]

export function GraphLegend() {
  return (
    <div className="graph-legend">
      <div className="graph-legend-title">Edge kinds</div>
      {EDGE_KINDS.map((kind) => (
        <div className="graph-legend-row" key={kind}>
          <span className="graph-legend-swatch" style={{ background: edgeColor(kind) }} />
          <span>{EDGE_LABEL[kind]}</span>
        </div>
      ))}
      <div className="graph-legend-title graph-legend-title-spaced">Node roles</div>
      <div className="graph-legend-row">
        <span className="graph-legend-node-sample role-entry" />
        <span>entry point — nothing calls it</span>
      </div>
      <div className="graph-legend-row">
        <span className="graph-legend-node-sample role-leaf" />
        <span>leaf — calls nothing itself</span>
      </div>
      <div className="graph-legend-row">
        <span className="graph-legend-node-sample role-dimmed" />
        <span>outside current scope</span>
      </div>
    </div>
  )
}
