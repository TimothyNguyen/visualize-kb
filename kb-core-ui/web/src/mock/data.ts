import type { CallEdgeEntry, Edge, StatsResponse, Symbol, SymbolRef, TreeNode } from "../api/types"

// A small fake 3-4 file TypeScript + Go mini-repo used to browse the app
// standalone (VITE_USE_MOCK=true) without a running Go backend.

export const MOCK_TREE: TreeNode = {
  path: "",
  name: "kb-core-demo",
  type: "dir",
  children: [
    {
      path: "src",
      name: "src",
      type: "dir",
      children: [
        { path: "src/index.ts", name: "index.ts", type: "file", language: "typescript" },
        { path: "src/server.ts", name: "server.ts", type: "file", language: "typescript" },
      ],
    },
    {
      path: "internal",
      name: "internal",
      type: "dir",
      children: [
        { path: "internal/models.go", name: "models.go", type: "file", language: "go" },
        { path: "internal/service.go", name: "service.go", type: "file", language: "go" },
      ],
    },
  ],
}

const CONFIG_PATH: Symbol = {
  id: "ts:src/index.ts:CONFIG_PATH",
  name: "CONFIG_PATH",
  kind: "const",
  filePath: "src/index.ts",
  startLine: 3,
  endLine: 3,
  signature: 'const CONFIG_PATH: string = "./config.json"',
  params: [],
  returns: [],
  language: "typescript",
}

const MAIN: Symbol = {
  id: "ts:src/index.ts:main",
  name: "main",
  kind: "function",
  filePath: "src/index.ts",
  startLine: 8,
  endLine: 11,
  signature: "function main(): void",
  params: [],
  returns: [{ name: "", type: "void" }],
  language: "typescript",
  doc: "main is the entrypoint for the KB Core demo service.",
}

const CONFIG_IFACE: Symbol = {
  id: "ts:src/server.ts:Config",
  name: "Config",
  kind: "interface",
  filePath: "src/server.ts",
  startLine: 1,
  endLine: 4,
  signature: "interface Config { port: number; host: string }",
  params: [],
  returns: [],
  language: "typescript",
}

const HANDLER_IFACE: Symbol = {
  id: "ts:src/server.ts:Handler",
  name: "Handler",
  kind: "interface",
  filePath: "src/server.ts",
  startLine: 6,
  endLine: 8,
  signature: "interface Handler { handleRequest(req: Request): Response }",
  params: [],
  returns: [],
  language: "typescript",
}

const START_SERVER: Symbol = {
  id: "ts:src/server.ts:startServer",
  name: "startServer",
  kind: "function",
  filePath: "src/server.ts",
  startLine: 13,
  endLine: 16,
  signature: "function startServer(config: Config): void",
  params: [{ name: "config", type: "Config" }],
  returns: [{ name: "", type: "void" }],
  language: "typescript",
  doc: "startServer boots the HTTP router and begins listening for connections.",
}

const ROUTER_CLASS: Symbol = {
  id: "ts:src/server.ts:Router",
  name: "Router",
  kind: "class",
  filePath: "src/server.ts",
  startLine: 18,
  endLine: 25,
  signature: "class Router implements Handler",
  params: [],
  returns: [],
  language: "typescript",
}

const ROUTER_HANDLE_REQUEST: Symbol = {
  id: "ts:src/server.ts:Router.handleRequest",
  name: "handleRequest",
  kind: "method",
  filePath: "src/server.ts",
  startLine: 22,
  endLine: 24,
  signature: "handleRequest(req: Request): Response",
  params: [{ name: "req", type: "Request" }],
  returns: [{ name: "", type: "Response" }],
  receiver: "Router",
  parentId: ROUTER_CLASS.id,
  language: "typescript",
  doc: "handleRequest dispatches an incoming request to the appropriate handler.",
}

const ADMIN_ROUTER_CLASS: Symbol = {
  id: "ts:src/server.ts:AdminRouter",
  name: "AdminRouter",
  kind: "class",
  filePath: "src/server.ts",
  startLine: 27,
  endLine: 28,
  signature: "class AdminRouter extends Router",
  params: [],
  returns: [],
  language: "typescript",
}

const DEFAULT_TIMEOUT: Symbol = {
  id: "go:internal/models.go:DefaultTimeout",
  name: "DefaultTimeout",
  kind: "const",
  filePath: "internal/models.go",
  startLine: 5,
  endLine: 5,
  signature: "const DefaultTimeout = 30",
  params: [],
  returns: [],
  language: "go",
  doc: "DefaultTimeout is the maximum duration, in seconds, allowed for a single\ndatabase query before it is cancelled.",
}

const USER_STRUCT: Symbol = {
  id: "go:internal/models.go:User",
  name: "User",
  kind: "class",
  filePath: "internal/models.go",
  startLine: 8,
  endLine: 11,
  signature: "type User struct { Name string; Email string }",
  params: [],
  returns: [],
  language: "go",
  doc: "User represents an application user record.",
}

const FETCH_USER: Symbol = {
  id: "go:internal/service.go:FetchUser",
  name: "FetchUser",
  kind: "function",
  filePath: "internal/service.go",
  startLine: 7,
  endLine: 14,
  signature: "func FetchUser(id string) (*User, error)",
  params: [{ name: "id", type: "string" }],
  returns: [
    { name: "", type: "*User" },
    { name: "err", type: "error" },
  ],
  language: "go",
  doc: "FetchUser retrieves a user by ID from the database, using a short-lived\nconnection from the pool.",
}

const QUERY_DB: Symbol = {
  id: "go:internal/service.go:queryDB",
  name: "queryDB",
  kind: "function",
  filePath: "internal/service.go",
  startLine: 17,
  endLine: 19,
  signature: "func queryDB(query string) (*sql.Rows, error)",
  params: [{ name: "query", type: "string" }],
  returns: [
    { name: "", type: "*sql.Rows" },
    { name: "", type: "error" },
  ],
  language: "go",
  doc: "queryDB executes a raw SQL query against the primary connection pool.",
}

export const ALL_SYMBOLS: Symbol[] = [
  CONFIG_PATH,
  MAIN,
  CONFIG_IFACE,
  HANDLER_IFACE,
  START_SERVER,
  ROUTER_CLASS,
  ROUTER_HANDLE_REQUEST,
  ADMIN_ROUTER_CLASS,
  DEFAULT_TIMEOUT,
  USER_STRUCT,
  FETCH_USER,
  QUERY_DB,
]

export const SYMBOLS_BY_ID: Record<string, Symbol> = Object.fromEntries(ALL_SYMBOLS.map((s) => [s.id, s]))

// Top-level symbols per file (excludes members like Router.handleRequest).
export const SYMBOLS_BY_FILE: Record<string, SymbolRef[]> = {
  "src/index.ts": [CONFIG_PATH, MAIN],
  "src/server.ts": [CONFIG_IFACE, HANDLER_IFACE, START_SERVER, ROUTER_CLASS, ADMIN_ROUTER_CLASS],
  "internal/models.go": [DEFAULT_TIMEOUT, USER_STRUCT],
  "internal/service.go": [FETCH_USER, QUERY_DB],
}

export const MEMBERS_BY_PARENT: Record<string, SymbolRef[]> = {
  [ROUTER_CLASS.id]: [ROUTER_HANDLE_REQUEST],
}

export const ALL_EDGES: Edge[] = [
  { source: MAIN.id, target: START_SERVER.id, kind: "calls" },
  { source: START_SERVER.id, target: ROUTER_HANDLE_REQUEST.id, kind: "calls" },
  { source: START_SERVER.id, target: CONFIG_IFACE.id, kind: "references" },
  { source: ROUTER_CLASS.id, target: ROUTER_HANDLE_REQUEST.id, kind: "contains" },
  { source: ROUTER_CLASS.id, target: HANDLER_IFACE.id, kind: "implements" },
  { source: ADMIN_ROUTER_CLASS.id, target: ROUTER_CLASS.id, kind: "extends" },
  { source: FETCH_USER.id, target: QUERY_DB.id, kind: "calls" },
  { source: FETCH_USER.id, target: USER_STRUCT.id, kind: "references" },
]

export function mockCalls(id: string): CallEdgeEntry[] {
  const result: CallEdgeEntry[] = []
  for (const edge of ALL_EDGES) {
    if (edge.source !== id) continue
    const symbol = SYMBOLS_BY_ID[edge.target]
    if (symbol) result.push({ edge, symbol })
  }
  return result
}

export function mockCallers(id: string): CallEdgeEntry[] {
  const result: CallEdgeEntry[] = []
  for (const edge of ALL_EDGES) {
    if (edge.target !== id) continue
    const symbol = SYMBOLS_BY_ID[edge.source]
    if (symbol) result.push({ edge, symbol })
  }
  return result
}

export function mockSubgraph(id: string, depth: number): { nodes: SymbolRef[]; edges: Edge[]; center: string } {
  const nodeIds = new Set<string>([id])
  let frontier = [id]
  for (let i = 0; i < depth; i++) {
    const next: string[] = []
    for (const nid of frontier) {
      for (const e of ALL_EDGES) {
        if (e.source === nid && !nodeIds.has(e.target)) {
          nodeIds.add(e.target)
          next.push(e.target)
        }
        if (e.target === nid && !nodeIds.has(e.source)) {
          nodeIds.add(e.source)
          next.push(e.source)
        }
      }
    }
    frontier = next
  }
  const nodes = [...nodeIds].map((nid) => SYMBOLS_BY_ID[nid]).filter(Boolean)
  const edges = ALL_EDGES.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
  return { nodes, edges, center: id }
}

export const MOCK_STATS: StatsResponse = {
  files: 4,
  symbols: ALL_SYMBOLS.length,
  edges: ALL_EDGES.length,
  languages: { typescript: 2, go: 2 },
}

export function mockSearch(q: string, kind?: string): SymbolRef[] {
  const query = q.trim().toLowerCase()
  return ALL_SYMBOLS.filter((s) => {
    const matchesQuery = query === "" || s.name.toLowerCase().includes(query)
    const matchesKind = !kind || s.kind === kind
    return matchesQuery && matchesKind
  })
}
