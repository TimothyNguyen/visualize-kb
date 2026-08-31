import { useEffect, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import type { CallEdgeEntry, Symbol as GraphSymbol, SymbolRef } from "../api/types"
import { getSymbol, getSymbolCallers, getSymbolCalls, getSymbolMembers } from "../api/client"
import { KindBadge, LanguageBadge } from "../components/Badges/Badges"
import { CodePanel } from "../components/CodePanel/CodePanel"
import { LocalSymbolGraph } from "../components/SymbolGraph/LocalSymbolGraph"
import { editorLink } from "../utils/editorLink"
import "./SymbolDetailView.css"

export function SymbolDetailView() {
  const { id = "" } = useParams()
  return <SymbolDetailContent key={id} id={id} />
}

function SymbolDetailContent({ id }: { id: string }) {
  const navigate = useNavigate()

  const [symbol, setSymbol] = useState<GraphSymbol | null>(null)
  const [members, setMembers] = useState<SymbolRef[]>([])
  const [calls, setCalls] = useState<CallEdgeEntry[]>([])
  const [callers, setCallers] = useState<CallEdgeEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([getSymbol(id), getSymbolMembers(id), getSymbolCalls(id), getSymbolCallers(id)])
      .then(([sym, mem, callsRes, callersRes]) => {
        if (cancelled) return
        setSymbol(sym)
        setMembers(mem)
        setCalls(callsRes)
        setCallers(callersRes)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load symbol")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [id])

  function goTo(symbolId: string) {
    navigate(`/symbol/${encodeURIComponent(symbolId)}`)
  }

  if (loading) return <div className="symbol-detail-status">Loading symbol…</div>
  if (error) return <div className="symbol-detail-status error">{error}</div>
  if (!symbol) return null

  return (
    <div className="symbol-detail">
      <div className="symbol-detail-header">
        <div className="symbol-detail-title-row">
          <LanguageBadge language={symbol.language} />
          <KindBadge kind={symbol.kind} />
          <h1 className="symbol-detail-name">{symbol.name}</h1>
        </div>
        <div className="symbol-detail-loc">
          <button type="button" className="loc-link" onClick={() => navigate(`/file/${symbol.filePath}`)}>
            {symbol.filePath}
          </button>
          <span>
            :{symbol.startLine}
            {symbol.endLine !== symbol.startLine ? `–${symbol.endLine}` : ""}
          </span>
          <a
            className="editor-link"
            href={editorLink(symbol.filePath, symbol.startLine)}
            title="Open in editor (vscode://)"
          >
            Open in editor ↗
          </a>
        </div>
      </div>

      {symbol.signature && <code className="symbol-detail-signature">{symbol.signature}</code>}

      {symbol.doc && <p className="symbol-detail-doc">{symbol.doc}</p>}

      <div className="symbol-detail-meta-grid">
        {symbol.receiver && (
          <MetaBlock title="Receiver">
            <code>{symbol.receiver}</code>
          </MetaBlock>
        )}
        <MetaBlock title="Params">
          {symbol.params.length === 0 ? (
            <span className="meta-empty">none</span>
          ) : (
            <ul className="param-list">
              {symbol.params.map((p, i) => (
                <li key={`${p.name}-${i}`}>
                  <span className="param-name">{p.name || `arg${i}`}</span>
                  {p.type && <span className="param-type">: {p.type}</span>}
                </li>
              ))}
            </ul>
          )}
        </MetaBlock>
        <MetaBlock title="Returns">
          {symbol.returns.length === 0 ? (
            <span className="meta-empty">none</span>
          ) : (
            <ul className="param-list">
              {symbol.returns.map((p, i) => (
                <li key={`${p.name}-${i}`}>
                  {p.name && <span className="param-name">{p.name}</span>}
                  {p.type && <span className="param-type">{p.name ? ": " : ""}{p.type}</span>}
                </li>
              ))}
            </ul>
          )}
        </MetaBlock>
      </div>

      {members.length > 0 && (
        <section className="symbol-detail-section">
          <h2>Members</h2>
          <div className="member-list">
            {members.map((m) => (
              <button type="button" key={m.id} className="member-row" onClick={() => goTo(m.id)}>
                <KindBadge kind={m.kind} />
                <span className="member-name">{m.name}</span>
                <span className="member-loc">
                  {m.filePath}:{m.startLine}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="symbol-detail-section">
        <h2>Call graph</h2>
        <LocalSymbolGraph symbol={symbol} callers={callers} calls={calls} />
      </section>

      <div className="symbol-detail-callist-grid">
        <section className="symbol-detail-section">
          <h2>Callers ({callers.length})</h2>
          <CallList entries={callers} onSelect={goTo} emptyLabel="No callers found." />
        </section>
        <section className="symbol-detail-section">
          <h2>Calls ({calls.length})</h2>
          <CallList entries={calls} onSelect={goTo} emptyLabel="This symbol does not call anything else." />
        </section>
      </div>

      <section className="symbol-detail-section">
        <h2>Source</h2>
        <CodePanel filePath={symbol.filePath} start={symbol.startLine} end={symbol.endLine} />
      </section>
    </div>
  )
}

function MetaBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="meta-block">
      <div className="meta-block-title">{title}</div>
      <div className="meta-block-body">{children}</div>
    </div>
  )
}

function CallList({
  entries,
  onSelect,
  emptyLabel,
}: {
  entries: CallEdgeEntry[]
  onSelect: (id: string) => void
  emptyLabel: string
}) {
  if (entries.length === 0) return <div className="call-list-empty">{emptyLabel}</div>
  return (
    <ul className="call-list">
      {entries.map(({ edge, symbol: s }) => (
        <li key={`${edge.source}-${edge.target}-${s.id}`}>
          <button type="button" className="call-row" onClick={() => onSelect(s.id)}>
            <span className={`edge-kind-tag edge-${edge.kind}`}>{edge.kind}</span>
            <KindBadge kind={s.kind} />
            <span className="call-row-name">{s.name}</span>
            <span className="call-row-loc">
              {s.filePath}:{s.startLine}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
