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

export interface IngestionRun {
  id: string
  workspace_id: string
  source_id: string
  status: IngestionStatus
  error: string
  result: Record<string, unknown>
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

export function getWorkspaceStats(workspaceId: string): Promise<WorkspaceStats> {
  return workspaceRequest(`/${encodeURIComponent(workspaceId)}/stats`)
}
