# KB Core UI REST API Contract (v1)

Base URL: `http://localhost:8420/api`

All responses are JSON. This contract is the single source of truth shared
between the Go backend (`internal/server`) and the web frontend (`web/`).
Do not diverge from field names/types below without updating this file.

## Core types

```ts
type SymbolKind =
  | "module"    // a source file
  | "package"   // a directory / package
  | "class"
  | "interface"
  | "function"
  | "method"
  | "const"
  | "variable"
  | "route"     // synthetic: a framework route-registration call site, not a declaration.
                 // name is the route pattern (e.g. "GET /api/tree"); an EdgeHandles
                 // edge points at the handler function.

interface Param {
  name: string
  type: string   // "" if unknown/untyped
}

interface SymbolRef {
  id: string          // stable id, e.g. "go:internal/graph/builder.go:BuildGraph"
  name: string
  kind: SymbolKind
  filePath: string     // repo-relative path
  startLine: number    // 1-indexed
  endLine: number
}

interface Symbol extends SymbolRef {
  signature: string        // rendered signature, e.g. "func BuildGraph(files []File) (*Graph, error)"
  params: Param[]          // inputs
  returns: Param[]         // outputs
  receiver?: string        // for methods, e.g. "*Builder"
  parentId?: string        // enclosing class/module symbol id
  language: string         // "go" | "typescript" | "javascript" | "python"
  doc?: string             // leading comment/docstring, if present
}

interface Edge {
  source: string   // symbol id
  target: string   // symbol id
  kind: "calls" | "references" | "contains" | "implements" | "extends" | "handles"
  // "handles": source is a KindRoute symbol, target is its handler function.
}

interface TreeNode {
  path: string             // repo-relative path, "" for repo root
  name: string
  type: "dir" | "file"
  language?: string        // set when type === "file"
  children?: TreeNode[]    // set when type === "dir"
}
```

## Endpoints

### `GET /tree`
Full repo file tree.
→ `TreeNode` (root)

### `GET /files/*path/symbols`
Top-level symbols declared in a file (functions, classes, consts, vars — not
nested members, use `/symbols/:id/members` for those).
→ `SymbolRef[]`

### `GET /symbols/:id`
Full detail for one symbol.
→ `Symbol`

### `GET /symbols/:id/members`
Child symbols (e.g. methods of a class).
→ `SymbolRef[]`

### `GET /symbols/:id/calls`
Outgoing edges: symbols this one calls/references.
→ `Array<{ edge: Edge, symbol: SymbolRef }>`

### `GET /symbols/:id/callers`
Incoming edges: symbols that call/reference this one.
→ `Array<{ edge: Edge, symbol: SymbolRef }>`

### `GET /graph`
Full graph (small/medium repos). Large repos should prefer `/graph/subgraph`.
→ `{ nodes: SymbolRef[], edges: Edge[] }`

### `GET /graph/subgraph?symbol=:id&depth=2`
BFS neighborhood of one symbol out to `depth` hops, both directions.
→ `{ nodes: SymbolRef[], edges: Edge[], center: string }`

### `GET /search?q=:query&kind=:kind` (kind optional)
Fuzzy symbol search by name.
→ `SymbolRef[]`

### `GET /source?file=:path&start=:n&end=:n`
Raw source lines `[start, end]` inclusive, 1-indexed, for the code panel.
→ `{ filePath: string, startLine: number, lines: string[] }`

### `GET /stats`
Repo-wide counts, shown in the UI header.
→ `{ files: number, symbols: number, edges: number, languages: Record<string, number> }`

## Bot control (dashboard)

Types:

```ts
interface BotDef {
  name: string          // stable id, e.g. "graph-sync"
  title: string         // human label, e.g. "Graph Sync"
  description: string
  kind: "go-native" | "python"
  needsAuth: boolean    // true if it needs a working `claude` session
  args: BotArg[]        // declared inputs the UI renders a form for
}

interface BotArg {
  name: string          // e.g. "pr_number"
  label: string
  required: boolean
  placeholder?: string
}

type RunStatus = "running" | "succeeded" | "failed"

interface BotRun {
  id: string            // opaque run id
  bot: string           // BotDef.name
  status: RunStatus
  startedAt: string     // RFC3339
  finishedAt?: string   // RFC3339, set when not running
  exitCode?: number     // set when finished
  output: string        // combined stdout+stderr so far (grows while running)
}

// A run summary omits `output` for cheap list rendering.
type BotRunSummary = Omit<BotRun, "output">
```

### `GET /bots`
List the available bots.
→ `BotDef[]`

### `POST /bots/:name/run`
Start a bot run. Body: `{ args?: Record<string, string> }` (keys are
`BotArg.name`). Returns the created run (status `"running"`).
→ `BotRun`  · 400 if a required arg is missing, 404 if the bot is unknown.

### `GET /bots/runs`
Recent runs, newest first (summaries, no output).
→ `BotRunSummary[]`

### `GET /bots/runs/:id`
One run with its full current output. The UI polls this while
`status === "running"` to stream output.
→ `BotRun`  · 404 if unknown.

## Vector memory

Non-code knowledge (rules, lessons, business logic, overviews) stored as
embeddings and searched semantically. Endpoints only exist when memory is
enabled (`kb-core-ui serve`).

```ts
type MemoryKind = "rule" | "lesson" | "business" | "overview" | "reference"

interface MemoryEntry {
  id: string
  kind: MemoryKind
  title: string
  text: string
  source?: string
  createdAt: string   // RFC3339
}

interface MemoryHit {
  entry: MemoryEntry
  score: number       // cosine similarity, higher = more relevant
}
```

### `GET /memory?kind=:kind` (kind optional)
List entries, newest first.
→ `MemoryEntry[]`

### `GET /memory/search?q=:query&kind=:kind&top=:n`
Semantic search; returns the most relevant entries.
→ `MemoryHit[]`

### `POST /memory`
Add an entry. Body: `{ kind, title, text, source? }`.
→ `MemoryEntry`  · 400 on invalid kind or missing title/text.

### `DELETE /memory/:id`
Remove an entry.
→ `{ removed: boolean }`  · 404 if unknown.

## Errors

Non-2xx responses body: `{ "error": string }`. 404 for unknown ids/paths, 400
for bad query params.

## Frontend notes

- Dev server proxies `/api/*` to `http://localhost:8420` (see `web/vite.config.ts`).
- Clicking any node/symbol in the graph or file tree should be able to resolve
  a `filePath` + `startLine` to open in an editor via a `kb-core-ui://open?file=..&line=..`
  link AND show inline source via `/source`. Both should be supported — the UI
  displays inline source in a CodePanel, and separately renders a "Open in editor"
  link/button using the same file/line, since the user wants to jump to source
  from an actual editor.
