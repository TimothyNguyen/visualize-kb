import { useCallback, useEffect, useState } from "react"
import type { BotDef, BotRun, BotRunSummary, RunStatus } from "../api/types"
import { getBotRun, getBotRuns, getBots, runBot } from "../api/client"
import "./BotsView.css"

const POLL_INTERVAL_MS = 1200

export function BotsView() {
  const [bots, setBots] = useState<BotDef[] | null>(null)
  const [botsError, setBotsError] = useState<string | null>(null)

  const [runs, setRuns] = useState<BotRunSummary[]>([])
  const [runsError, setRunsError] = useState<string | null>(null)

  const [selectedRun, setSelectedRun] = useState<BotRun | null>(null)
  const [outputError, setOutputError] = useState<string | null>(null)

  // Which bot's inline arg form is currently open (bot.name), and its values.
  const [openForm, setOpenForm] = useState<string | null>(null)
  const [argValues, setArgValues] = useState<Record<string, string>>({})
  const [startingBot, setStartingBot] = useState<string | null>(null)

  const botByName = useCallback(
    (name: string): BotDef | undefined => bots?.find((b) => b.name === name),
    [bots],
  )

  const loadRuns = useCallback(async () => {
    try {
      const list = await getBotRuns()
      setRuns(list)
      setRunsError(null)
    } catch (err: unknown) {
      setRunsError(err instanceof Error ? err.message : "failed to load run history")
    }
  }, [])

  // Initial load of bot definitions + run history.
  useEffect(() => {
    let cancelled = false
    getBots()
      .then((list) => {
        if (!cancelled) {
          setBots(list)
          setBotsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setBotsError(err instanceof Error ? err.message : "failed to load bots")
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getBotRuns()
      .then((list) => {
        if (!cancelled) {
          setRuns(list)
          setRunsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setRunsError(err instanceof Error ? err.message : "failed to load run history")
      })
    return () => {
      cancelled = true
    }
  }, [])

  // --- Live polling of the selected run while it is running. ---
  // The effect re-runs whenever the selected run id or status changes. While
  // status === "running" it installs a 1.2s interval that re-fetches the run
  // and updates output/status. When status flips to a terminal value the deps
  // change, the cleanup clears the interval, and the effect returns early — so
  // polling stops. The cleanup also runs on unmount / when switching runs, so
  // no interval is ever leaked.
  const selectedId = selectedRun?.id
  const selectedStatus = selectedRun?.status
  useEffect(() => {
    if (!selectedId || selectedStatus !== "running") return
    let cancelled = false
    const interval = window.setInterval(async () => {
      try {
        const updated = await getBotRun(selectedId)
        if (cancelled) return
        setSelectedRun((prev) => (prev && prev.id === selectedId ? updated : prev))
        setOutputError(null)
        if (updated.status !== "running") {
          // A run just finished: refresh the history list so its status pill updates.
          void loadRuns()
        }
      } catch (err: unknown) {
        if (!cancelled) setOutputError(err instanceof Error ? err.message : "failed to poll run")
      }
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [loadRuns, selectedId, selectedStatus])

  function toggleForm(bot: BotDef) {
    if (openForm === bot.name) {
      setOpenForm(null)
      return
    }
    setOpenForm(bot.name)
    // Seed the form with empty values for each declared arg.
    const seed: Record<string, string> = {}
    for (const arg of bot.args) seed[arg.name] = ""
    setArgValues(seed)
  }

  async function startRun(bot: BotDef, args: Record<string, string>) {
    setStartingBot(bot.name)
    setOutputError(null)
    try {
      const run = await runBot(bot.name, args)
      setSelectedRun(run)
      setOpenForm(null)
      // Refresh history so the new (running) run appears at the top.
      loadRuns()
    } catch (err: unknown) {
      setOutputError(err instanceof Error ? err.message : "failed to start run")
    } finally {
      setStartingBot(null)
    }
  }

  function handleRunClick(bot: BotDef) {
    if (bot.args.length === 0) {
      startRun(bot, {})
    } else {
      toggleForm(bot)
    }
  }

  function submitForm(e: React.FormEvent, bot: BotDef) {
    e.preventDefault()
    startRun(bot, argValues)
  }

  async function selectRun(id: string) {
    setOutputError(null)
    try {
      const run = await getBotRun(id)
      setSelectedRun(run)
    } catch (err: unknown) {
      setOutputError(err instanceof Error ? err.message : "failed to load run")
    }
  }

  return (
    <div className="bots-view">
      <div className="bots-header">
        <h1 className="bots-title">Bots</h1>
        <p className="bots-subtitle">Run maintenance and analysis bots against this repo.</p>
      </div>

      {botsError && <div className="bots-error">{botsError}</div>}

      <section className="bots-list-section">
        {!bots && !botsError && <div className="bots-loading">Loading bots…</div>}
        {bots && bots.length === 0 && <div className="bots-empty">No bots are registered.</div>}
        <div className="bot-card-list">
          {bots?.map((bot) => (
            <BotCard
              key={bot.name}
              bot={bot}
              open={openForm === bot.name}
              starting={startingBot === bot.name}
              argValues={openForm === bot.name ? argValues : {}}
              onRunClick={() => handleRunClick(bot)}
              onArgChange={(name, value) => setArgValues((prev) => ({ ...prev, [name]: value }))}
              onSubmit={(e) => submitForm(e, bot)}
            />
          ))}
        </div>
      </section>

      <div className="bots-body">
        <section className="bots-output-region">
          <OutputPanel
            run={selectedRun}
            botTitle={selectedRun ? (botByName(selectedRun.bot)?.title ?? selectedRun.bot) : ""}
            error={outputError}
          />
        </section>

        <aside className="bots-history">
          <h2 className="bots-history-title">Run history</h2>
          {runsError && <div className="bots-error">{runsError}</div>}
          {!runsError && runs.length === 0 && <div className="bots-empty">No runs yet.</div>}
          <ul className="run-history-list">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={`run-history-row ${selectedId === r.id ? "selected" : ""}`}
                  onClick={() => selectRun(r.id)}
                >
                  <span className="run-history-name">{botByName(r.bot)?.title ?? r.bot}</span>
                  <StatusPill status={r.status} />
                  <span className="run-history-time">{shortTime(r.startedAt)}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  )
}

function BotCard({
  bot,
  open,
  starting,
  argValues,
  onRunClick,
  onArgChange,
  onSubmit,
}: {
  bot: BotDef
  open: boolean
  starting: boolean
  argValues: Record<string, string>
  onRunClick: () => void
  onArgChange: (name: string, value: string) => void
  onSubmit: (e: React.FormEvent) => void
}) {
  return (
    <div className="bot-card">
      <div className="bot-card-top">
        <span className="bot-card-title">{bot.title}</span>
        <span className={`badge bot-kind-badge bot-kind-${bot.kind}`}>{bot.kind}</span>
      </div>
      <p className="bot-card-desc">{bot.description}</p>
      <div className="bot-card-meta">
        {bot.needsAuth && <span className="badge bot-auth-badge">needs claude auth</span>}
      </div>

      {open && bot.args.length > 0 ? (
        <form className="bot-arg-form" onSubmit={onSubmit}>
          {bot.args.map((arg) => (
            <label key={arg.name} className="bot-arg-field">
              <span className="bot-arg-label">
                {arg.label}
                {arg.required && <span className="bot-arg-required"> *</span>}
              </span>
              <input
                className="bot-arg-input"
                value={argValues[arg.name] ?? ""}
                placeholder={arg.placeholder}
                required={arg.required}
                onChange={(e) => onArgChange(arg.name, e.target.value)}
              />
            </label>
          ))}
          <div className="bot-arg-actions">
            <button type="submit" className="bot-run-button" disabled={starting}>
              {starting ? "Starting…" : "Run"}
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="bot-run-button" onClick={onRunClick} disabled={starting}>
          {starting ? "Starting…" : "Run"}
        </button>
      )}
    </div>
  )
}

function OutputPanel({
  run,
  botTitle,
  error,
}: {
  run: BotRun | null
  botTitle: string
  error: string | null
}) {
  if (!run) {
    return (
      <div className="output-panel empty">
        {error ? (
          <div className="bots-error">{error}</div>
        ) : (
          <p className="output-placeholder">Select a bot to run, or pick a run from the history.</p>
        )}
      </div>
    )
  }

  return (
    <div className="output-panel">
      <div className="output-head">
        <div className="output-head-main">
          <span className="output-bot-title">{botTitle}</span>
          <StatusPill status={run.status} />
        </div>
        <div className="output-head-meta">
          <span>started {formatTime(run.startedAt)}</span>
          {run.finishedAt && <span>finished {formatTime(run.finishedAt)}</span>}
          {run.status !== "running" && run.exitCode !== undefined && (
            <span className={`output-exit ${run.exitCode === 0 ? "ok" : "bad"}`}>
              exit {run.exitCode}
            </span>
          )}
        </div>
      </div>
      {error && <div className="bots-error output-inline-error">{error}</div>}
      <pre className="output-console">{run.output || "(no output yet)"}</pre>
    </div>
  )
}

function StatusPill({ status }: { status: RunStatus }) {
  return <span className={`status-pill status-${status}`}>{status}</span>
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

// Short relative-ish label for the history list.
function shortTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const diffMs = Date.now() - d.getTime()
  const sec = Math.round(diffMs / 1000)
  if (sec < 60) return `${Math.max(sec, 0)}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 7) return `${day}d ago`
  return d.toLocaleDateString()
}
