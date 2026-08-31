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

// --- Workspace GraphRAG chat ---
// The wire shapes frozen under kb-core-ui/contracts/rag-chat/v1, which the
// server regenerates and byte-compares on every test run. Field names stay
// snake_case because these are the server payloads verbatim.

export type ChatStrategy = "auto" | "local" | "multi_path"
export type ChatEvidenceOrigin = "retrieval" | "graph"
export type ChatFeedbackRating = "up" | "down"

export interface ChatEvidence {
  id: string
  source_id: string
  text: string
  source_location: string
  score: number
  origin: ChatEvidenceOrigin
}

export interface ChatCitation {
  evidence_id: string
  source_id: string
  source_location: string
  origin: ChatEvidenceOrigin
}

export interface ChatExplainGraphNode {
  id: string
  source_id: string
  label: string
  source_location: string
}

export interface ChatExplainGraphEdge {
  source: string
  target: string
  relation: string
}

export interface ChatExplainGraph {
  nodes: ChatExplainGraphNode[]
  edges: ChatExplainGraphEdge[]
}

export interface ChatSourceMapEntry {
  source_id: string
  source_location: string
  origin: ChatEvidenceOrigin
}

// One finished answer. Identical whether it arrives from POST /chat, the
// terminal `completed` SSE event, or a turn replayed out of thread history.
export interface ChatAnswer {
  workspace_id: string
  query_id: string
  answer: string
  citations: ChatCitation[]
  context: ChatEvidence[] // the evidence the answer is grounded in
  explain_graph: ChatExplainGraph
  source_map: Record<string, ChatSourceMapEntry> // evidence id -> source
  strategy: ChatStrategy
  degraded: boolean // graph expansion failed; vector evidence survived
  insufficient_evidence: boolean
  errors: string[] // non-fatal workflow notes, never provider internals
  timings: Record<string, number> // per-node seconds
  error: string // "" unless the request itself failed
}

export interface ChatAskRequest {
  query: string
  thread_id?: string
  allowed_source_ids?: string[]
  strategy?: ChatStrategy
  requested_k?: number
  requested_graph_row_limit?: number
  query_id?: string
}

export interface ChatTurn {
  turn_id: string
  thread_id: string
  workspace_id: string
  seq: number // 1-based, monotonic within the thread
  query: string
  response: ChatAnswer
  created_at: string // RFC3339
}

export interface ChatThread {
  workspace_id: string
  thread_id: string
  turns: ChatTurn[]
}

export interface ChatSuggestions {
  workspace_id: string
  suggestions: string[]
  recent_queries: string[]
}

export interface ChatFeedbackEntry {
  query_id: string
  workspace_id: string
  rating: ChatFeedbackRating
  comment: string
  created_at: string // RFC3339
}

export interface ChatCancelResult {
  query_id: string
  workspace_id: string
  cancelled: boolean // false when the query had already finished
  reason?: string
}

export interface ChatSourceMapResponse {
  workspace_id: string
  query_id: string
  source_map: Record<string, ChatSourceMapEntry>
}

export interface ChatExplainGraphResponse {
  workspace_id: string
  query_id: string
  explain_graph: ChatExplainGraph
}

export interface ChatThreadDeleted {
  workspace_id: string
  thread_id: string
  deleted: boolean
}

export interface ChatThreadsDeleted {
  workspace_id: string
  deleted_threads: number
}

// SSE frames. Heartbeats are SSE comments, so they are dropped by the parser
// and never appear here. Exactly one terminal event ends a stream.
export type ChatStreamEvent =
  | { event: "queued"; data: { query_id: string; workspace_id: string } }
  | { event: "token"; data: { query_id: string; text: string } }
  | { event: "completed"; data: ChatAnswer }
  | { event: "cancelled"; data: { query_id: string; workspace_id: string } }
  | { event: "error"; data: { query_id: string; workspace_id: string; status: number; message: string } }

export type ChatTerminalEvent = Extract<ChatStreamEvent, { event: "completed" | "cancelled" | "error" }>
