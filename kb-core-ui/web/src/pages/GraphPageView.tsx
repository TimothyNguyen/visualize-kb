import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import type { Edge, GraphResponse, SubgraphResponse, SymbolRef } from "../api/types"
import { getGraph, getSubgraph, search } from "../api/client"
import { GlobalGraph } from "../components/GlobalGraph/GlobalGraph"
import "./GraphPageView.css"

export function GraphPageView() {
  const [searchParams, setSearchParams] = useSearchParams()
  const focusSymbol = searchParams.get("symbol") ?? ""
  const depth = Number(searchParams.get("depth") ?? "2")

  const [nodes, setNodes] = useState<SymbolRef[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [center, setCenter] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [query, setQuery] = useState(focusSymbol)
  const [suggestions, setSuggestions] = useState<SymbolRef[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    async function load() {
      if (focusSymbol) {
        const res: SubgraphResponse = await getSubgraph(focusSymbol, depth)
        if (cancelled) return
        setNodes(res.nodes)
        setEdges(res.edges)
        setCenter(res.center)
      } else {
        const res: GraphResponse = await getGraph()
        if (cancelled) return
        setNodes(res.nodes)
        setEdges(res.edges)
        setCenter(undefined)
      }
    }

    load()
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load graph")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [focusSymbol, depth])

  useEffect(() => {
    if (!query || query === focusSymbol) {
      setSuggestions([])
      return
    }
    let cancelled = false
    search(query).then((r) => {
      if (!cancelled) setSuggestions(r.slice(0, 8))
    })
    return () => {
      cancelled = true
    }
  }, [query, focusSymbol])

  function focusOn(id: string) {
    setSearchParams(id ? { symbol: id, depth: String(depth) } : {})
    setQuery(id)
    setSuggestions([])
  }

  return (
    <div className="graph-page">
      <div className="graph-page-toolbar">
        <h1 className="graph-page-title">{focusSymbol ? "Focus mode" : "Full call graph"}</h1>
        <div className="graph-focus-search">
          <input
            placeholder="Focus on a symbol…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {suggestions.length > 0 && (
            <div className="graph-focus-suggestions">
              {suggestions.map((s) => (
                <button type="button" key={s.id} onClick={() => focusOn(s.id)}>
                  {s.name} <span>{s.filePath}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        {focusSymbol && (
          <>
            <label className="graph-depth-control">
              depth
              <select
                value={depth}
                onChange={(e) => setSearchParams({ symbol: focusSymbol, depth: e.target.value })}
              >
                {[1, 2, 3, 4].map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="graph-clear-focus" onClick={() => focusOn("")}>
              Show full graph
            </button>
          </>
        )}
      </div>

      <div className="graph-page-canvas">
        {loading && <div className="graph-page-status">Loading graph…</div>}
        {error && <div className="graph-page-status error">{error}</div>}
        {!loading && !error && <GlobalGraph nodes={nodes} edges={edges} centerId={center} />}
      </div>
    </div>
  )
}
