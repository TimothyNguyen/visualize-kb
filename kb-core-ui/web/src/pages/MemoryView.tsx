import { useEffect, useState } from "react"
import type { MemoryEntry, MemoryHit, MemoryKind } from "../api/types"
import { addMemory, deleteMemory, getMemory, searchMemory } from "../api/client"
import "./MemoryView.css"

const KINDS: MemoryKind[] = ["rule", "lesson", "business", "overview", "reference"]
const SEARCH_DEBOUNCE_MS = 300

type KindFilter = MemoryKind | "any"

export function MemoryView() {
  const [query, setQuery] = useState("")
  const [kindFilter, setKindFilter] = useState<KindFilter>("any")

  // Full list (shown when the search box is empty) and search hits (shown otherwise).
  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [hits, setHits] = useState<MemoryHit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Bumped after add/delete to force the currently-active view to reload.
  const [refreshKey, setRefreshKey] = useState(0)

  const searching = query.trim().length > 0

  // Load the full list OR run a search depending on whether the box has text.
  // While searching we debounce ~300ms; when the box is empty we fetch the list
  // immediately. The effect cleanup clears any pending timer AND flips a
  // `cancelled` flag, so switching the query/filter mid-flight never leaks a
  // timer and never lands an out-of-date response into state.
  useEffect(() => {
    let cancelled = false
    const kind = kindFilter === "any" ? undefined : kindFilter
    const q = query.trim()

    if (q.length === 0) {
      getMemory(kind)
        .then((list) => {
          if (cancelled) return
          setEntries(list)
          setError(null)
        })
        .catch((err: unknown) => {
          if (!cancelled) setError(err instanceof Error ? err.message : "failed to load memory")
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
      return () => {
        cancelled = true
      }
    }

    const timer = window.setTimeout(() => {
      searchMemory(q, kind)
        .then((results) => {
          if (cancelled) return
          setHits(results)
          setError(null)
        })
        .catch((err: unknown) => {
          if (!cancelled) setError(err instanceof Error ? err.message : "failed to search memory")
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, SEARCH_DEBOUNCE_MS)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query, kindFilter, refreshKey])

  function refresh() {
    setLoading(true)
    setRefreshKey((k) => k + 1)
  }

  async function handleDelete(id: string) {
    setError(null)
    try {
      await deleteMemory(id)
      refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "failed to delete entry")
    }
  }

  return (
    <div className="memory-view">
      <div className="memory-header">
        <h1 className="memory-title">Memory</h1>
        <p className="memory-subtitle">
          Non-code knowledge — rules, lessons, business logic and overviews — searched semantically.
        </p>
      </div>

      <form className="memory-search" onSubmit={(e) => e.preventDefault()}>
        <input
          className="memory-search-input"
          type="search"
          value={query}
          placeholder="Search memory…"
          onChange={(e) => {
            setLoading(true)
            setQuery(e.target.value)
          }}
        />
        <select
          className="memory-kind-select"
          value={kindFilter}
          onChange={(e) => {
            setLoading(true)
            setKindFilter(e.target.value as KindFilter)
          }}
        >
          <option value="any">any kind</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </form>

      {error && <div className="memory-error">{error}</div>}

      <AddMemoryForm onAdded={refresh} onError={setError} />

      <section className="memory-results">
        {loading ? (
          <div className="memory-empty">Loading…</div>
        ) : searching ? (
          hits.length === 0 ? (
            <div className="memory-empty">No relevant memory found.</div>
          ) : (
            <div className="memory-card-list">
              {hits.map((hit) => (
                <MemoryCard
                  key={hit.entry.id}
                  entry={hit.entry}
                  score={hit.score}
                  onDelete={() => handleDelete(hit.entry.id)}
                />
              ))}
            </div>
          )
        ) : entries.length === 0 ? (
          <div className="memory-empty">No memory yet — add the codebase's rules and lessons.</div>
        ) : (
          <div className="memory-card-list">
            {entries.map((entry) => (
              <MemoryCard
                key={entry.id}
                entry={entry}
                onDelete={() => handleDelete(entry.id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function AddMemoryForm({
  onAdded,
  onError,
}: {
  onAdded: () => void
  onError: (msg: string | null) => void
}) {
  const [kind, setKind] = useState<MemoryKind>("rule")
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [source, setSource] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = title.trim().length > 0 && text.trim().length > 0 && !submitting

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (title.trim().length === 0 || text.trim().length === 0) return
    setSubmitting(true)
    onError(null)
    try {
      await addMemory({
        kind,
        title: title.trim(),
        text: text.trim(),
        source: source.trim() || undefined,
      })
      setTitle("")
      setText("")
      setSource("")
      onAdded()
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "failed to add entry")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="memory-add" onSubmit={submit}>
      <div className="memory-add-row">
        <select
          className="memory-add-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as MemoryKind)}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input
          className="memory-add-title"
          value={title}
          placeholder="Title"
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <textarea
        className="memory-add-text"
        value={text}
        placeholder="Text — the rule, lesson or note to remember…"
        rows={4}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="memory-add-row">
        <input
          className="memory-add-source"
          value={source}
          placeholder="Source (optional)"
          onChange={(e) => setSource(e.target.value)}
        />
        <button type="submit" className="memory-add-button" disabled={!canSubmit}>
          {submitting ? "Adding…" : "Add"}
        </button>
      </div>
    </form>
  )
}

function MemoryCard({
  entry,
  score,
  onDelete,
}: {
  entry: MemoryEntry
  score?: number
  onDelete: () => void
}) {
  return (
    <div className="memory-card">
      <div className="memory-card-top">
        <div className="memory-card-heading">
          {score !== undefined && <span className="memory-score">{score.toFixed(2)}</span>}
          <span className="memory-card-title">{entry.title}</span>
          <span className={`badge memory-kind-badge memory-kind-${entry.kind}`}>{entry.kind}</span>
        </div>
        <button
          type="button"
          className="memory-delete"
          title="Delete entry"
          aria-label="Delete entry"
          onClick={onDelete}
        >
          ×
        </button>
      </div>
      <p className="memory-card-text">{entry.text}</p>
      <div className="memory-card-meta">
        {entry.source && <span className="memory-card-source">{entry.source}</span>}
        <span className="memory-card-time">{formatTime(entry.createdAt)}</span>
      </div>
    </div>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}
