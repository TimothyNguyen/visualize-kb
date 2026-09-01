import { ApiRequestError, SERVICE_API_BASE } from "./client"

export type WorkspaceSourceKind = "local_repo" | "document_set"
export type IngestionStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled"

export interface WorkspaceSource {
  id: string
  workspace_id: string
  kind: string
  uri: string
  ref: string
  status: string
  active_version: string
}

// One record the normalizer refused, so the operator can see what was dropped
// instead of silently getting a smaller graph.
export interface RejectedRecord {
  record_type: string
  index: number
  record_id: string
  reason: string
}

export interface IngestionResult {
  reconcile_status?: string
  version?: string
  counts?: { nodes: number; relationships: number; chunks: number; citations: number }
  rejected?: RejectedRecord[]
}

export interface IngestionRun {
  id: string
  workspace_id: string
  source_id: string
  status: IngestionStatus
  error: string
  result: IngestionResult
}

export const TERMINAL_RUN_STATUSES: readonly IngestionStatus[] = ["succeeded", "failed", "cancelled"]

export function isRunTerminal(run: IngestionRun): boolean {
  return TERMINAL_RUN_STATUSES.includes(run.status)
}

export interface Workspace {
  id: string
  name: string
  graph_name: string
  status: string
  sources: Record<string, WorkspaceSource>
  runs: Record<string, IngestionRun>
}

export interface WorkspaceStats {
  workspace_id: string
  nodes: number
  relationships: number
  source_ids: string[]
}

async function workspaceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${SERVICE_API_BASE}/rag/workspaces${path}`, init)
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new ApiRequestError(response.status, body?.error || response.statusText)
  }
  return response.json() as Promise<T>
}

function postJson(body?: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

export function listWorkspaces(): Promise<Workspace[]> {
  return workspaceRequest("")
}

export function createWorkspace(id: string, name: string): Promise<Workspace> {
  return workspaceRequest("", postJson({ id, name }))
}

export function addWorkspaceSource(
  workspaceId: string,
  source: { id: string; kind: WorkspaceSourceKind; uri: string; ref?: string },
): Promise<WorkspaceSource> {
  return workspaceRequest(
    `/${encodeURIComponent(workspaceId)}/sources`,
    postJson({ ...source, ref: source.ref ?? "" }),
  )
}

export function startWorkspaceIngestion(workspaceId: string, sourceId: string): Promise<IngestionRun> {
  return workspaceRequest(
    `/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/ingestions`,
    postJson(),
  )
}

export function refreshWorkspaceSource(workspaceId: string, sourceId: string): Promise<IngestionRun> {
  return workspaceRequest(
    `/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/refresh`,
    postJson(),
  )
}

export interface SourceDeletion {
  workspace_id: string
  source_id: string
  deleted: boolean
}

export function removeWorkspaceSource(workspaceId: string, sourceId: string): Promise<SourceDeletion> {
  return workspaceRequest(
    `/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  )
}

export function getIngestionRun(workspaceId: string, runId: string): Promise<IngestionRun> {
  return workspaceRequest(`/${encodeURIComponent(workspaceId)}/runs/${encodeURIComponent(runId)}`)
}

export function cancelIngestionRun(workspaceId: string, runId: string): Promise<IngestionRun> {
  return workspaceRequest(
    `/${encodeURIComponent(workspaceId)}/runs/${encodeURIComponent(runId)}/cancel`,
    postJson(),
  )
}

export function getWorkspaceStats(workspaceId: string): Promise<WorkspaceStats> {
  return workspaceRequest(`/${encodeURIComponent(workspaceId)}/stats`)
}

export interface WorkspaceContextRecord {
  source_identity: string
  label: string
  node_type: string
  source_id: string
  text: string
  source_location: string
}

export interface WorkspaceContextEdge {
  source: string
  target: string
  relation: string
  source_id: string
}

export interface WorkspaceContext {
  workspace_id: string
  source_ids: string[]
  limit: number
  focus: string
  records: WorkspaceContextRecord[]
  edges: WorkspaceContextEdge[]
}

export function getWorkspaceContext(
  workspaceId: string,
  options: { sourceIds?: string[]; limit?: number; focus?: string } = {},
): Promise<WorkspaceContext> {
  const query = new URLSearchParams()
  if (options.limit) query.set("limit", String(options.limit))
  for (const sourceId of options.sourceIds ?? []) query.append("source", sourceId)
  if (options.focus) query.set("focus", options.focus)
  const suffix = query.size > 0 ? `?${query}` : ""
  return workspaceRequest(`/${encodeURIComponent(workspaceId)}/context${suffix}`)
}

export interface ChatMemoryEntry {
  id: string
  workspace_id: string
  thread_id: string
  turn_id: string
  seq: number
  title: string
  text: string
  source: string
  created_at: string
}

export interface ChatMemoryHit {
  entry: ChatMemoryEntry
  score: number
}

function chatMemoryPath(workspaceId: string, threadId?: string): string {
  const query = new URLSearchParams()
  if (threadId) query.set("thread", threadId)
  const suffix = query.size > 0 ? `?${query}` : ""
  return `/${encodeURIComponent(workspaceId)}/memory${suffix}`
}

export async function listChatMemories(
  workspaceId: string,
  threadId?: string,
): Promise<ChatMemoryEntry[]> {
  const body = await workspaceRequest<{ entries: ChatMemoryEntry[] }>(
    chatMemoryPath(workspaceId, threadId),
  )
  return body.entries ?? []
}

export async function searchChatMemories(
  workspaceId: string,
  query: string,
  top = 5,
): Promise<ChatMemoryHit[]> {
  const params = new URLSearchParams({ q: query, top: String(top) })
  const body = await workspaceRequest<{ hits: ChatMemoryHit[] }>(
    `/${encodeURIComponent(workspaceId)}/memory/search?${params}`,
  )
  return body.hits ?? []
}

export async function deleteChatMemories(workspaceId: string, threadId?: string): Promise<number> {
  const body = await workspaceRequest<{ deleted: number }>(chatMemoryPath(workspaceId, threadId), {
    method: "DELETE",
  })
  return body.deleted ?? 0
}
