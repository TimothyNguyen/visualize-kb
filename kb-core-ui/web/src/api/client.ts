import type {
  CallEdgeEntry,
  BotDef,
  BotRun,
  BotRunSummary,
  Edge,
  EdgeKind,
  GraphResponse,
  SourceResponse,
  StatsResponse,
  SubgraphResponse,
  Symbol,
  SymbolKind,
  SymbolRef,
  TreeNode,
  MemoryEntry,
  MemoryHit,
  MemoryKind,
} from "./types"

type KbCoreNode = {
  id: string
  label?: string
  source_file?: string
  source_location?: string
  signature?: string
  doc?: string
  description?: string
}

type KbCoreEdge = { source: string; target: string; relation?: string }
type KbCoreGraph = { nodes: KbCoreNode[]; edges: KbCoreEdge[] }
type KbCoreGraphFile = { nodes?: KbCoreNode[]; edges?: KbCoreEdge[]; links?: KbCoreEdge[] }

const GRAPH_URL = import.meta.env.VITE_KB_CORE_GRAPH_URL || "/kb-core-out/graph.json"
const GRAPH_OVERVIEW_URL = import.meta.env.VITE_KB_CORE_GRAPH_OVERVIEW_URL || "/kb-core-out/graph-overview.json"
const SERVICE_API_BASE = import.meta.env.VITE_KB_CORE_UI_API_URL || "/api"
let graphPromise: Promise<KbCoreGraph> | undefined
let overviewPromise: Promise<KbCoreGraph> | undefined

export class ApiRequestError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiRequestError"
    this.status = status
  }
}

function loadGraph(): Promise<KbCoreGraph> {
  graphPromise ??= fetch(GRAPH_URL).then(async (res) => {
    if (!res.ok) {
      throw new ApiRequestError(
        res.status,
        `Could not load KB Core graph at ${GRAPH_URL}. Run kb-core extract, then copy kb-core-out/graph.json into public/kb-core-out/.`,
      )
    }
    const raw = (await res.json()) as KbCoreGraphFile
    // NetworkX's node-link exporter calls this array "links". Older KB Core
    // consumers use "edges", so accept both and normalize at this boundary.
    const graph: KbCoreGraph = {
      nodes: raw.nodes ?? [],
      edges: raw.edges ?? raw.links ?? [],
    }
    if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new ApiRequestError(422, "KB Core graph.json has an invalid shape")
    }
    return graph
  })
  return graphPromise
}

function parseGraphResponse(res: Response): Promise<KbCoreGraph> {
  return res.json().then((raw: KbCoreGraphFile) => {
    const graph: KbCoreGraph = {
      nodes: raw.nodes ?? [],
      edges: raw.edges ?? raw.links ?? [],
    }
    if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new ApiRequestError(422, "KB Core graph.json has an invalid shape")
    }
    return graph
  })
}

function loadOverview(): Promise<KbCoreGraph> {
  overviewPromise ??= fetch(GRAPH_OVERVIEW_URL).then(async (res) => {
    if (!res.ok) return loadGraph()
    return parseGraphResponse(res)
  })
  return overviewPromise
}

function lineNumber(location?: string): number {
  return Number(location?.match(/\d+/)?.[0] ?? 1)
}

function language(filePath: string): string {
  const extension = filePath.split(".").pop()?.toLowerCase()
  return ({ py: "python", go: "go", ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript" })[extension ?? ""] ?? "text"
}

function kind(node: KbCoreNode): SymbolKind {
  const label = node.label ?? node.id
  if (node.source_file && (label === node.source_file || label === node.source_file.split("/").pop())) return "module"
  if (label.startsWith(".")) return "method"
  if (label.endsWith("()")) return "function"
  if (/^[A-Z][A-Za-z0-9_]*$/.test(label)) return "class"
  return "variable"
}

function toRef(node: KbCoreNode): SymbolRef {
  const filePath = node.source_file ?? ""
  const startLine = lineNumber(node.source_location)
  return { id: node.id, name: node.label ?? node.id, kind: kind(node), filePath, startLine, endLine: startLine }
}

function toSymbol(node: KbCoreNode): Symbol {
  return {
    ...toRef(node),
    signature: node.signature ?? "",
    params: [],
    returns: [],
    language: language(node.source_file ?? ""),
    doc: node.doc ?? node.description ?? "",
  }
}

function edgeKind(relation?: string): EdgeKind {
  if (relation === "calls") return "calls"
  if (relation === "contains" || relation === "method") return "contains"
  if (relation === "inherits") return "extends"
  if (relation === "implements") return "implements"
  if (relation === "handles") return "handles"
  return "references"
}

function toEdge(edge: KbCoreEdge): Edge {
  return { source: edge.source, target: edge.target, kind: edgeKind(edge.relation) }
}

function byId(graph: KbCoreGraph): Map<string, KbCoreNode> {
  return new Map(graph.nodes.map((node) => [node.id, node]))
}

export async function getGraph(): Promise<GraphResponse> {
  const graph = await loadGraph()
  return { nodes: graph.nodes.map(toRef), edges: graph.edges.map(toEdge) }
}

export async function getGraphOverview(): Promise<GraphResponse> {
  const graph = await loadOverview()
  return { nodes: graph.nodes.map(toRef), edges: graph.edges.map(toEdge) }
}

export async function getSymbol(id: string): Promise<Symbol> {
  const node = byId(await loadGraph()).get(id)
  if (!node) throw new ApiRequestError(404, `Symbol ${id} was not found in KB Core graph`)
  return toSymbol(node)
}

export async function getFileSymbols(filePath: string): Promise<SymbolRef[]> {
  return (await loadGraph()).nodes
    .filter((node) => node.source_file === filePath)
    .map(toRef)
    .filter((node) => node.kind !== "module")
}

export async function getSymbolMembers(id: string): Promise<SymbolRef[]> {
  const graph = await loadGraph()
  const nodes = byId(graph)
  return graph.edges
    .filter((edge) => edge.source === id && edgeKind(edge.relation) === "contains")
    .map((edge) => nodes.get(edge.target))
    .filter((node): node is KbCoreNode => Boolean(node))
    .map(toRef)
}

function callEntries(graph: KbCoreGraph, id: string, direction: "out" | "in"): CallEdgeEntry[] {
  const nodes = byId(graph)
  return graph.edges
    .filter((edge) => edgeKind(edge.relation) === "calls")
    .filter((edge) => (direction === "out" ? edge.source === id : edge.target === id))
    .map((edge) => {
      const other = nodes.get(direction === "out" ? edge.target : edge.source)
      return other ? { edge: toEdge(edge), symbol: toRef(other) } : undefined
    })
    .filter((entry): entry is CallEdgeEntry => Boolean(entry))
}

export async function getSymbolCalls(id: string): Promise<CallEdgeEntry[]> {
  return callEntries(await loadGraph(), id, "out")
}

export async function getSymbolCallers(id: string): Promise<CallEdgeEntry[]> {
  return callEntries(await loadGraph(), id, "in")
}

export async function getSubgraph(symbolId: string, depth = 2): Promise<SubgraphResponse> {
  const graph = await loadGraph()
  if (!byId(graph).has(symbolId)) throw new ApiRequestError(404, `Symbol ${symbolId} was not found in KB Core graph`)
  const adjacent = new Map<string, string[]>()
  for (const edge of graph.edges) {
    adjacent.set(edge.source, [...(adjacent.get(edge.source) ?? []), edge.target])
    adjacent.set(edge.target, [...(adjacent.get(edge.target) ?? []), edge.source])
  }
  const ids = new Set([symbolId])
  let frontier = [symbolId]
  for (let level = 0; level < depth; level += 1) {
    const next = frontier.flatMap((id) => adjacent.get(id) ?? []).filter((id) => !ids.has(id))
    next.forEach((id) => ids.add(id))
    frontier = next
  }
  return {
    nodes: graph.nodes.filter((node) => ids.has(node.id)).map(toRef),
    edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)).map(toEdge),
    center: symbolId,
  }
}

export async function search(q: string, kindFilter?: SymbolKind): Promise<SymbolRef[]> {
  const needle = q.toLowerCase()
  return (await loadGraph()).nodes
    .map(toRef)
    .filter((node) => !kindFilter || node.kind === kindFilter)
    .filter((node) => `${node.name} ${node.filePath}`.toLowerCase().includes(needle))
}

export async function getTree(): Promise<TreeNode> {
  const root: TreeNode = { path: "", name: "KB Core", type: "dir", children: [] }
  for (const node of (await loadGraph()).nodes) {
    const path = node.source_file
    if (!path) continue
    const parts = path.split("/")
    let parent = root
    parts.forEach((part, index) => {
      const currentPath = parts.slice(0, index + 1).join("/")
      const type = index === parts.length - 1 ? "file" : "dir"
      let child = parent.children?.find((entry) => entry.path === currentPath)
      if (!child) {
        child = { path: currentPath, name: part, type, ...(type === "dir" ? { children: [] } : { language: language(path) }) }
        parent.children?.push(child)
      }
      parent = child
    })
  }
  const sort = (node: TreeNode) => {
    node.children?.sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name))
    node.children?.forEach(sort)
  }
  sort(root)
  return root
}

export async function getStats(): Promise<StatsResponse> {
  const graph = await loadGraph()
  const files = new Set(graph.nodes.map((node) => node.source_file).filter((file): file is string => Boolean(file)))
  const languages: Record<string, number> = {}
  files.forEach((file) => {
    const key = language(file)
    languages[key] = (languages[key] ?? 0) + 1
  })
  return { files: files.size, symbols: graph.nodes.length, edges: graph.edges.length, languages }
}

export async function getSource(filePath: string, start: number, _end: number): Promise<SourceResponse> {
  return { filePath, startLine: start, lines: ["Source text is not embedded in KB Core graph.json. Open this file in your editor."] }
}

async function serviceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${SERVICE_API_BASE}${path}`, init)
  if (!response.ok) throw new ApiRequestError(response.status, response.statusText)
  return response.json() as Promise<T>
}

export function getBots(): Promise<BotDef[]> { return serviceRequest("/bots") }

export function runBot(name: string, args: Record<string, string>): Promise<BotRun> {
  return serviceRequest(`/bots/${encodeURIComponent(name)}/run`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ args }),
  })
}

export function getBotRuns(): Promise<BotRunSummary[]> { return serviceRequest("/bots/runs") }
export function getBotRun(id: string): Promise<BotRun> { return serviceRequest(`/bots/runs/${encodeURIComponent(id)}`) }

export function getMemory(kind?: MemoryKind): Promise<MemoryEntry[]> {
  return serviceRequest(`/memory${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`)
}

export function searchMemory(q: string, kind?: MemoryKind, top?: number): Promise<MemoryHit[]> {
  const params = new URLSearchParams({ q })
  if (kind) params.set("kind", kind)
  if (top !== undefined) params.set("top", String(top))
  return serviceRequest(`/memory/search?${params}`)
}

export function addMemory(input: { kind: MemoryKind; title: string; text: string; source?: string }): Promise<MemoryEntry> {
  return serviceRequest("/memory", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  })
}

export function deleteMemory(id: string): Promise<{ removed: boolean }> {
  return serviceRequest(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" })
}
