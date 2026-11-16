const STORAGE_KEY = "kb-core-ui.workspace-scope"

export interface WorkspaceScope {
  workspaceId: string
  sourceIds: string[]
}

const EMPTY_SCOPE: WorkspaceScope = { workspaceId: "", sourceIds: [] }

export function readWorkspaceScope(): WorkspaceScope {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_SCOPE
    const value = JSON.parse(raw) as Partial<WorkspaceScope>
    return {
      workspaceId: typeof value.workspaceId === "string" ? value.workspaceId : "",
      sourceIds: Array.isArray(value.sourceIds)
        ? value.sourceIds.filter((id): id is string => typeof id === "string")
        : [],
    }
  } catch {
    return EMPTY_SCOPE
  }
}

export function writeWorkspaceScope(scope: WorkspaceScope): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
    workspaceId: scope.workspaceId,
    sourceIds: [...new Set(scope.sourceIds)],
  }))
}
