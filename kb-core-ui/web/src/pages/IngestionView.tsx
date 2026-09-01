import { useCallback, useEffect, useState, type FormEvent } from "react"

import {
  addWorkspaceSource,
  getIngestionRun,
  getWorkspaceStats,
  lookupFolder,
  isRunTerminal,
  listWorkspaces,
  refreshWorkspaceSource,
  removeWorkspaceSource,
  startWorkspaceIngestion,
  type IngestionRun,
  type Workspace,
  type WorkspaceSourceKind,
  type WorkspaceStats,
} from "../api/workspaces"
import { readWorkspaceScope, writeWorkspaceScope } from "../utils/workspaceScope"
import "./IngestionView.css"

const POLL_INTERVAL_MS = 60

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed"
}

export function IngestionView() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState("")
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [run, setRun] = useState<IngestionRun | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState("")
  const [selectedSourceId, setSelectedSourceId] = useState("")
  const [folder, setFolder] = useState<{ path: string; parent: string; directories: { name: string; path: string }[] } | null>(null)
  const [folderError, setFolderError] = useState("")
  const [draft, setDraft] = useState<{ id: string; kind: WorkspaceSourceKind; uri: string }>({
    id: "",
    kind: "local_repo",
    uri: "",
  })

  const selected = workspaces.find((workspace) => workspace.id === workspaceId)
  const sources = selected ? Object.values(selected.sources) : []
  const counts = run?.result?.counts
  const rejected = run?.result?.rejected ?? []
  const runStatus = run?.status ?? ""
  const failure = error || (run?.status === "failed" ? run.error : "")

  const load = useCallback(
    () =>
      listWorkspaces().then((items) => {
        setWorkspaces(items)
        const scope = readWorkspaceScope()
        setWorkspaceId((current) =>
          items.some((item) => item.id === current)
            ? current
            : (items.some((item) => item.id === scope.workspaceId) ? scope.workspaceId : (items[0]?.id ?? "")),
        )
        const scopedWorkspace = items.find((item) => item.id === scope.workspaceId) ?? items[0]
        setSelectedSourceId(scope.sourceIds.find((id) => scopedWorkspace?.sources[id]) ?? Object.keys(scopedWorkspace?.sources ?? {})[0] ?? "")
      }),
    [],
  )

  useEffect(() => {
    load().catch((failed: unknown) => setError(errorMessage(failed)))
  }, [load])

  useEffect(() => {
    if (!workspaceId) return
    let active = true
    getWorkspaceStats(workspaceId)
      .then((value) => active && setStats(value))
      .catch(() => active && setStats(null))
    return () => {
      active = false
    }
  }, [workspaceId, runStatus])

  // Polling is the only way the browser learns a run finished, so it has to stop
  // itself on both terminal state and unmount rather than leak a timer per run.
  useEffect(() => {
    if (!run || isRunTerminal(run)) return
    let active = true
    const timer = setTimeout(() => {
      getIngestionRun(run.workspace_id, run.id)
        .then((next) => active && setRun(next))
        .catch((failed: unknown) => active && setError(errorMessage(failed)))
    }, POLL_INTERVAL_MS)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [run])

  function selectWorkspace(id: string): void {
    setWorkspaceId(id)
    setStats(null)
    setRun(null)
    setError("")
    const next = workspaces.find((workspace) => workspace.id === id)
    const sourceId = Object.keys(next?.sources ?? {})[0] ?? ""
    setSelectedSourceId(sourceId)
    writeWorkspaceScope({ workspaceId: id, sourceIds: sourceId ? [sourceId] : [] })
  }

  function selectSource(id: string): void {
    setSelectedSourceId(id)
    writeWorkspaceScope({ workspaceId, sourceIds: id ? [id] : [] })
  }

  async function browse(path = ""): Promise<void> {
    setFolderError("")
    try {
      setFolder(await lookupFolder(path))
    } catch (failed) {
      setFolderError(errorMessage(failed))
    }
  }

  async function guard(token: string, action: () => Promise<void>): Promise<void> {
    setBusy(token)
    setError("")
    try {
      await action()
    } catch (failed) {
      setError(errorMessage(failed))
    } finally {
      setBusy("")
    }
  }

  async function submitSource(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!workspaceId) return
    await guard("source", async () => {
      await addWorkspaceSource(workspaceId, {
        id: draft.id.trim(),
        kind: draft.kind,
        uri: draft.uri.trim(),
      })
      await load()
      selectSource(draft.id.trim())
      setDraft({ id: "", kind: draft.kind, uri: "" })
    })
  }

  return (
    <div className="ingestion-page">
      <header className="ingestion-heading">
        <p className="eyebrow">Internal GraphRAG</p>
        <h1>Ingestion</h1>
        <p>Index a local repo graph or document folder into a workspace graph.</p>
      </header>

      <label className="field-label" htmlFor="ingestion-workspace">Workspace</label>
      <select
        id="ingestion-workspace"
        value={workspaceId}
        onChange={(event) => selectWorkspace(event.target.value)}
      >
        <option value="">No workspace</option>
        {workspaces.map((workspace) => (
          <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
        ))}
      </select>

      <div className="workspace-stats" aria-label="Workspace graph statistics">
        <span><b>{stats?.nodes ?? 0}</b> nodes</span>
        <span><b>{stats?.relationships ?? 0}</b> relationships</span>
        <span><b>{sources.length}</b> sources</span>
      </div>

      <form className="compact-form" onSubmit={submitSource}>
        <h2>Add source</h2>
        <input
          aria-label="Source ID"
          placeholder="repo-api"
          pattern="[a-z][a-z0-9-]{0,62}"
          required
          value={draft.id}
          onChange={(event) => setDraft({ ...draft, id: event.target.value })}
        />
        <select
          aria-label="Source kind"
          value={draft.kind}
          onChange={(event) => setDraft({ ...draft, kind: event.target.value as WorkspaceSourceKind })}
        >
          <option value="local_repo">Local repo graph</option>
          <option value="document_set">Document folder</option>
        </select>
        <input
          aria-label="Source path"
          placeholder="C:/src/repo or C:/docs"
          required
          value={draft.uri}
          onChange={(event) => setDraft({ ...draft, uri: event.target.value })}
        />
        <button type="button" onClick={() => void browse(draft.uri.trim())} disabled={busy !== ""}>Lookup folder</button>
        <button type="submit" disabled={busy !== ""}>{busy === "source" ? "Adding..." : "Add source"}</button>
      </form>

      {folder && (
        <section className="folder-picker" aria-label="Folder lookup">
          <div className="folder-picker-heading">
            <b>Folder lookup</b>
            <code>{folder.path}</code>
          </div>
          <button type="button" onClick={() => void browse(folder.parent)} disabled={folder.parent === folder.path}>Up</button>
          <div className="folder-list">
            {folder.directories.map((directory) => (
              <button key={directory.path} type="button" onClick={() => {
                setDraft((current) => ({ ...current, uri: directory.path }))
                void browse(directory.path)
              }}>
                {directory.name}/
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setDraft((current) => ({ ...current, uri: folder.path }))}>Use this folder</button>
        </section>
      )}
      {folderError && <div className="workspace-error" role="alert">{folderError}</div>}

      <section className="source-list" aria-label="Workspace sources">
        <h2>Sources</h2>
        {sources.length === 0 && <p className="empty-note">No sources yet.</p>}
        {sources.map((source) => (
          <div className="source-row" key={source.id}>
            <input
              type="radio"
              name="selected-source"
              aria-label={`Use ${source.id}`}
              checked={selectedSourceId === source.id}
              onChange={() => selectSource(source.id)}
            />
            <span className="source-id">{source.id}</span>
            <span className="source-uri">{source.uri}</span>
            <span className={`source-status status-${source.status}`}>{source.status}</span>
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void guard(source.id, async () => setRun(await startWorkspaceIngestion(workspaceId, source.id)))
              }
            >
              Ingest
            </button>
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void guard(source.id, async () => setRun(await refreshWorkspaceSource(workspaceId, source.id)))
              }
            >
              Refresh
            </button>
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void guard(source.id, async () => {
                  await removeWorkspaceSource(workspaceId, source.id)
                  await load()
                })
              }
            >
              Delete
            </button>
          </div>
        ))}
      </section>

      {run && (
        <section className="run-panel" aria-label="Ingestion run">
          <h2>Run</h2>
          <p className="run-line">
            <code>{run.id}</code>
            <span className={`source-status status-${run.status}`}>{run.status}</span>
            {run.result?.reconcile_status && <span className="run-reconcile">{run.result.reconcile_status}</span>}
          </p>
          {counts && (
            <p className="run-counts">
              {`${counts.nodes} nodes, ${counts.relationships} relationships, ${counts.chunks} chunks, ${counts.citations} citations`}
            </p>
          )}
          {rejected.length > 0 && (
            <div className="rejected-report">
              {/* A published run with a smaller graph than expected is only
                  explainable if the dropped records are named here. */}
              <h3>Rejected records</h3>
              {rejected.map((record) => (
                <div className="rejected-row" key={`${record.record_type}-${record.index}`}>
                  <code>{record.record_id}</code>
                  <span>{record.record_type}</span>
                  <span>{record.reason}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {failure && <div className="workspace-error" role="alert">{failure}</div>}
    </div>
  )
}
