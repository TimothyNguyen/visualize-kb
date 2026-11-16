import { useEffect, useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { CopilotChat, CopilotKit, UseAgentUpdate, useAgent } from "@copilotkit/react-core/v2"
import "@copilotkit/react-core/v2/styles.css"

import type { ChatAnswer, ChatStrategy } from "../api/types"
import {
  addWorkspaceSource,
  createWorkspace,
  getWorkspaceStats,
  listWorkspaces,
  startWorkspaceIngestion,
  type Workspace,
  type WorkspaceSourceKind,
  type WorkspaceStats,
} from "../api/workspaces"
import { citationRoute } from "../utils/workspaceGraph"
import { readWorkspaceScope, writeWorkspaceScope } from "../utils/workspaceScope"
import "./WorkspaceChatView.css"

type AgentState = {
  workspace_id?: string
  strategy?: ChatStrategy
  allowed_source_ids?: string[]
  last_answer?: ChatAnswer
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed"
}

export function WorkspaceChatView() {
  return (
    <CopilotKit runtimeUrl={import.meta.env.VITE_COPILOTKIT_RUNTIME_URL || "/api/copilotkit"}>
      <WorkspaceChatWorkbench />
    </CopilotKit>
  )
}

function WorkspaceChatWorkbench() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState("")
  const [strategy, setStrategy] = useState<ChatStrategy>("auto")
  const [allowedSourceIds, setAllowedSourceIds] = useState<string[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState("")
  const [workspaceDraft, setWorkspaceDraft] = useState({ id: "", name: "" })
  const [sourceDraft, setSourceDraft] = useState<{ id: string; kind: WorkspaceSourceKind; uri: string }>({
    id: "",
    kind: "local_repo",
    uri: "",
  })
  const { agent, isReady } = useAgent({
    agentId: "kb-core",
    updates: [UseAgentUpdate.OnStateChanged],
    throttleMs: 100,
  })

  const selected = workspaces.find((workspace) => workspace.id === workspaceId)
  const sources = selected ? Object.values(selected.sources) : []
  const agentState = agent.state as AgentState
  const lastAnswer = agentState.last_answer

  useEffect(() => {
    let active = true
    listWorkspaces()
      .then((items) => {
        if (!active) return
        setWorkspaces(items)
        const scope = readWorkspaceScope()
        const opened = items.find((item) => item.id === scope.workspaceId) ?? items[0]
        if (!opened) return
        setWorkspaceId(opened.id)
        // Seed the scope so the checkboxes show the sources the agent is
        // actually allowed to read, rather than reading as an empty scope.
        const available = Object.keys(opened.sources)
        setAllowedSourceIds(scope.sourceIds.filter((id) => available.includes(id)).length > 0
          ? scope.sourceIds.filter((id) => available.includes(id))
          : available)
      })
      .catch((failure: unknown) => active && setError(errorMessage(failure)))
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!isReady || !workspaceId) return
    const previous = agent.state && typeof agent.state === "object" ? agent.state : {}
    agent.setState({
      ...previous,
      workspace_id: workspaceId,
      strategy,
      allowed_source_ids: allowedSourceIds,
    })
  }, [agent, allowedSourceIds, isReady, strategy, workspaceId])

  useEffect(() => {
    if (!workspaceId) return
    let active = true
    getWorkspaceStats(workspaceId)
      .then((value) => active && setStats(value))
      .catch(() => active && setStats(null))
    return () => {
      active = false
    }
  }, [workspaceId, workspaces])

  async function refresh(preferredWorkspaceId = workspaceId): Promise<void> {
    const items = await listWorkspaces()
    setWorkspaces(items)
    setWorkspaceId(items.some((item) => item.id === preferredWorkspaceId) ? preferredWorkspaceId : (items[0]?.id ?? ""))
  }

  function selectWorkspace(id: string): void {
    setWorkspaceId(id)
    setStats(null)
    const next = workspaces.find((workspace) => workspace.id === id)
    setAllowedSourceIds(next ? Object.keys(next.sources) : [])
    writeWorkspaceScope({ workspaceId: id, sourceIds: next ? Object.keys(next.sources) : [] })
    setError("")
  }

  async function submitWorkspace(event: FormEvent): Promise<void> {
    event.preventDefault()
    setBusy("workspace")
    setError("")
    try {
      await createWorkspace(workspaceDraft.id.trim(), workspaceDraft.name.trim())
      await refresh(workspaceDraft.id.trim())
      setWorkspaceDraft({ id: "", name: "" })
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy("")
    }
  }

  async function submitSource(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!workspaceId) return
    setBusy("source")
    setError("")
    try {
      await addWorkspaceSource(workspaceId, {
        id: sourceDraft.id.trim(),
        kind: sourceDraft.kind,
        uri: sourceDraft.uri.trim(),
      })
      await refresh()
      setAllowedSourceIds((current) => [...new Set([...current, sourceDraft.id.trim()])])
      writeWorkspaceScope({ workspaceId, sourceIds: [...new Set([...allowedSourceIds, sourceDraft.id.trim()])] })
      setSourceDraft({ id: "", kind: sourceDraft.kind, uri: "" })
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy("")
    }
  }

  async function ingest(sourceId: string): Promise<void> {
    setBusy(sourceId)
    setError("")
    try {
      await startWorkspaceIngestion(workspaceId, sourceId)
      await refresh()
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setBusy("")
    }
  }

  function toggleSource(sourceId: string): void {
    setAllowedSourceIds((current) => {
      const next = current.includes(sourceId) ? current.filter((id) => id !== sourceId) : [...current, sourceId]
      writeWorkspaceScope({ workspaceId, sourceIds: next })
      return next
    })
  }

  return (
    <div className="workspace-chat-page">
      <section className="workspace-rail" aria-label="Knowledge base controls">
        <div className="workspace-heading">
          <p className="eyebrow">Internal GraphRAG</p>
          <h1>Knowledge workspaces</h1>
          <p>Index local repo graphs or document sets. Browser never receives FalkorDB or model credentials.</p>
        </div>

        <label className="field-label" htmlFor="workspace-select">Workspace</label>
        <select id="workspace-select" value={workspaceId} onChange={(event) => selectWorkspace(event.target.value)}>
          <option value="">Create a workspace</option>
          {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
        </select>

        <form className="compact-form" onSubmit={submitWorkspace}>
          <h2>New workspace</h2>
          <input
            aria-label="Workspace ID"
            placeholder="repo-platform"
            pattern="[a-z][a-z0-9-]{0,62}"
            required
            value={workspaceDraft.id}
            onChange={(event) => setWorkspaceDraft({ ...workspaceDraft, id: event.target.value })}
          />
          <input
            aria-label="Workspace name"
            placeholder="Repo platform"
            required
            value={workspaceDraft.name}
            onChange={(event) => setWorkspaceDraft({ ...workspaceDraft, name: event.target.value })}
          />
          <button type="submit" disabled={busy !== ""}>{busy === "workspace" ? "Creating..." : "Create"}</button>
        </form>

        {selected && (
          <>
            <div className="workspace-stats" aria-label="Workspace graph statistics">
              <span><b>{stats?.nodes ?? 0}</b> nodes</span>
              <span><b>{stats?.relationships ?? 0}</b> edges</span>
              <span><b>{sources.length}</b> sources</span>
            </div>

            <form className="compact-form" onSubmit={submitSource}>
              <h2>Add source</h2>
              <input
                aria-label="Source ID"
                placeholder="repo-api"
                pattern="[a-z][a-z0-9-]{0,62}"
                required
                value={sourceDraft.id}
                onChange={(event) => setSourceDraft({ ...sourceDraft, id: event.target.value })}
              />
              <select
                aria-label="Source kind"
                value={sourceDraft.kind}
                onChange={(event) => setSourceDraft({ ...sourceDraft, kind: event.target.value as WorkspaceSourceKind })}
              >
                <option value="local_repo">Local repo graph</option>
                <option value="document_set">Document folder</option>
              </select>
              <input
                aria-label="Source path"
                placeholder="C:/src/repo or C:/docs"
                required
                value={sourceDraft.uri}
                onChange={(event) => setSourceDraft({ ...sourceDraft, uri: event.target.value })}
              />
              <button type="submit" disabled={busy !== ""}>{busy === "source" ? "Adding..." : "Add source"}</button>
            </form>

            <div className="source-list">
              <h2>Retrieval scope</h2>
              {sources.length === 0 && <p className="empty-note">No sources yet.</p>}
              {sources.map((source) => (
                <div className="source-row" key={source.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={allowedSourceIds.includes(source.id)}
                      onChange={() => toggleSource(source.id)}
                    />
                    <span>{source.id}</span>
                  </label>
                  <span className={`source-status status-${source.status}`}>{source.status}</span>
                  <button type="button" disabled={busy !== ""} onClick={() => void ingest(source.id)}>
                    {busy === source.id ? "Running..." : "Ingest"}
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
        {error && <div className="workspace-error" role="alert">{error}</div>}
      </section>

      <section className="chat-workbench" aria-label="Knowledge base chat">
        <div className="chat-toolbar">
          <div>
            <p className="eyebrow">Workspace analyst</p>
            <strong>{selected?.name ?? "No workspace selected"}</strong>
            <small className="scope-indicator">
              Scope: {allowedSourceIds.length === 0 ? "no sources" : allowedSourceIds.join(", ")}
            </small>
          </div>
          <label>
            Retrieval
            <select value={strategy} onChange={(event) => setStrategy(event.target.value as ChatStrategy)}>
              <option value="auto">Auto</option>
              <option value="local">Local</option>
              <option value="multi_path">Multi-path</option>
            </select>
          </label>
          <span className={`runtime-state ${isReady ? "ready" : "connecting"}`}>
            {isReady ? "Runtime ready" : "Connecting"}
          </span>
        </div>

        <div className="chat-surface">
          {selected ? (
            <CopilotChat key={selected.id} agentId="kb-core" />
          ) : (
            <div className="chat-empty">
              <span>01</span>
              <h2>Create workspace, add source, run ingestion.</h2>
              <p>Chat unlocks only after workspace scope exists.</p>
            </div>
          )}
        </div>

        <aside className="evidence-strip" aria-label="Latest answer citations">
          <div>
            <p className="eyebrow">Grounding</p>
            <strong>{lastAnswer ? `${lastAnswer.citations.length} citations` : "No answer yet"}</strong>
          </div>
          {lastAnswer?.insufficient_evidence && <span className="evidence-warning">Insufficient evidence</span>}
          {lastAnswer?.citations.map((citation) => {
            const route = citationRoute(citation, workspaceId)
            const label = citation.source_location || citation.evidence_id
            const key = `${citation.evidence_id}-${citation.source_location}`
            return route ? (
              <Link className="citation-chip" key={key} to={route}>
                <b>{citation.source_id}</b>
                {label}
              </Link>
            ) : (
              <span className="citation-chip" key={key}>
                <b>{citation.source_id}</b>
                {label}
                <i>no target</i>
              </span>
            )
          })}
        </aside>
      </section>
    </div>
  )
}
