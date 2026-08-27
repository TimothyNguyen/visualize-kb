// UI-normalized types derived from KB Core graph.json.

export type SymbolKind =
  | "module" // a source file
  | "package" // a directory / package
  | "class"
  | "interface"
  | "function"
  | "method"
  | "const"
  | "variable"
  | "route" // synthetic: a framework route-registration call site, not a declaration.
  // name is the route pattern (e.g. "GET /api/tree"); a "handles" edge points at the handler.

export interface Param {
  name: string
  type: string // "" if unknown/untyped
}

export interface SymbolRef {
  id: string // stable id, e.g. "go:internal/graph/builder.go:BuildGraph"
  name: string
  kind: SymbolKind
  filePath: string // repo-relative path
  startLine: number // 1-indexed
  endLine: number
}

export interface Symbol extends SymbolRef {
  signature: string // rendered signature, e.g. "func BuildGraph(files []File) (*Graph, error)"
  params: Param[] // inputs
  returns: Param[] // outputs
  receiver?: string // for methods, e.g. "*Builder"
  parentId?: string // enclosing class/module symbol id
  language: string // "go" | "typescript" | "javascript" | "python"
  doc?: string // leading comment/docstring, if present
}

export type EdgeKind = "calls" | "references" | "contains" | "implements" | "extends" | "handles"

export interface Edge {
  source: string // symbol id
  target: string // symbol id
  kind: EdgeKind
}

export interface TreeNode {
  path: string // repo-relative path, "" for repo root
  name: string
  type: "dir" | "file"
  language?: string // set when type === "file"
  children?: TreeNode[] // set when type === "dir"
}

export interface CallEdgeEntry {
  edge: Edge
  symbol: SymbolRef
}

export interface GraphResponse {
  nodes: SymbolRef[]
  edges: Edge[]
}

export interface SubgraphResponse extends GraphResponse {
  center: string
}

export interface SourceResponse {
  filePath: string
  startLine: number
  lines: string[]
}

export interface StatsResponse {
  files: number
  symbols: number
  edges: number
  languages: Record<string, number>
}

export interface ApiError {
  error: string
}

// --- Bot control (dashboard) ---
// Types copied verbatim from API_CONTRACT.md ("Bot control (dashboard)").

export interface BotDef {
  name: string // stable id, e.g. "graph-sync"
  title: string // human label, e.g. "Graph Sync"
  description: string
  kind: "go-native" | "python"
  needsAuth: boolean // true if it needs a working `claude` session
  args: BotArg[] // declared inputs the UI renders a form for
}

export interface BotArg {
  name: string // e.g. "pr_number"
  label: string
  required: boolean
  placeholder?: string
}

export type RunStatus = "running" | "succeeded" | "failed"

export interface BotRun {
  id: string // opaque run id
  bot: string // BotDef.name
  status: RunStatus
  startedAt: string // RFC3339
  finishedAt?: string // RFC3339, set when not running
  exitCode?: number // set when finished
  output: string // combined stdout+stderr so far (grows while running)
}

// A run summary omits `output` for cheap list rendering.
export type BotRunSummary = Omit<BotRun, "output">

// --- Vector memory ---
// Types copied verbatim from API_CONTRACT.md ("Vector memory").

export type MemoryKind = "rule" | "lesson" | "business" | "overview" | "reference"

export interface MemoryEntry {
  id: string
  kind: MemoryKind
  title: string
  text: string
  source?: string
  createdAt: string // RFC3339
}

export interface MemoryHit {
  entry: MemoryEntry
  score: number // cosine similarity, higher = more relevant
}
