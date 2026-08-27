import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import type { Symbol as GraphSymbol, SymbolKind, SymbolRef } from "../api/types"
import { getFileSymbols, getSymbol } from "../api/client"
import { KindBadge, LanguageBadge } from "../components/Badges/Badges"
import "./ModuleView.css"

const GROUP_ORDER: SymbolKind[] = ["route", "class", "interface", "function", "method", "const", "variable", "module", "package"]

const GROUP_TITLE: Record<SymbolKind, string> = {
  route: "Routes",
  class: "Classes",
  interface: "Interfaces",
  function: "Functions",
  method: "Methods",
  const: "Constants",
  variable: "Variables",
  module: "Modules",
  package: "Packages",
}

export function ModuleView() {
  const params = useParams()
  const filePath = params["*"] ?? ""
  const navigate = useNavigate()
  const [symbols, setSymbols] = useState<SymbolRef[] | null>(null)
  // The list endpoint only returns SymbolRef (no signature). We enrich each
  // entry with its full Symbol (via GET /symbols/:id) so the card can show a
  // type signature, per the module-view requirement.
  const [signatures, setSignatures] = useState<Record<string, GraphSymbol>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setSymbols(null)
    setSignatures({})
    setError(null)
    getFileSymbols(filePath)
      .then((s) => {
        if (cancelled) return
        setSymbols(s)
        Promise.all(
          s.map((ref) =>
            getSymbol(ref.id)
              .then((full) => [ref.id, full] as const)
              .catch(() => null),
          ),
        ).then((entries) => {
          if (cancelled) return
          const map: Record<string, GraphSymbol> = {}
          for (const entry of entries) {
            if (entry) map[entry[0]] = entry[1]
          }
          setSignatures(map)
        })
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load symbols")
      })
    return () => {
      cancelled = true
    }
  }, [filePath])

  const grouped = new Map<SymbolKind, SymbolRef[]>()
  for (const s of symbols ?? []) {
    const list = grouped.get(s.kind) ?? []
    list.push(s)
    grouped.set(s.kind, list)
  }

  return (
    <div className="module-view">
      <div className="module-header">
        <LanguageBadge language={inferLanguage(filePath)} />
        <h1 className="module-path">{filePath}</h1>
      </div>

      {error && <div className="module-error">{error}</div>}
      {!symbols && !error && <div className="module-loading">Loading symbols…</div>}
      {symbols && symbols.length === 0 && <div className="module-empty">No top-level symbols found in this file.</div>}

      {GROUP_ORDER.map((kind) => {
        const list = grouped.get(kind)
        if (!list || list.length === 0) return null
        return (
          <section className="module-group" key={kind}>
            <h2 className="module-group-title">{GROUP_TITLE[kind]}</h2>
            <div className="symbol-card-list">
              {list.map((s) => {
                const full = signatures[s.id]
                return (
                  <button
                    type="button"
                    key={s.id}
                    className="symbol-card"
                    onClick={() => navigate(`/symbol/${encodeURIComponent(s.id)}`)}
                  >
                    <div className="symbol-card-top">
                      <span className="symbol-card-name">{s.name}</span>
                      <KindBadge kind={s.kind} />
                    </div>
                    {full?.signature && <code className="symbol-card-signature">{full.signature}</code>}
                    <div className="symbol-card-loc">
                      {s.filePath}:{s.startLine}
                      {s.endLine !== s.startLine ? `–${s.endLine}` : ""}
                    </div>
                  </button>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function inferLanguage(filePath: string): string | undefined {
  if (filePath.endsWith(".go")) return "go"
  if (filePath.endsWith(".ts") || filePath.endsWith(".tsx")) return "typescript"
  if (filePath.endsWith(".js") || filePath.endsWith(".jsx")) return "javascript"
  if (filePath.endsWith(".py")) return "python"
  return undefined
}
