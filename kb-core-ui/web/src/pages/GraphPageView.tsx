import { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import type { Edge, GraphResponse, SubgraphResponse, SymbolRef } from "../api/types"
import { getGraph, getGraphOverview, getSubgraph, search } from "../api/client"
import { GlobalGraph } from "../components/GlobalGraph/GlobalGraph"
import "./GraphPageView.css"

export function GraphPageView() {
  const [searchParams] = useSearchParams()
  const focusSymbol = searchParams.get("symbol") ?? ""
  const depth = Number(searchParams.get("depth") ?? "2")
  return <GraphPageContent key={`${focusSymbol}:${depth}`} focusSymbol={focusSymbol} depth={depth} />
}

function GraphPageContent({ focusSymbol, depth }: { focusSymbol: string; depth: number }) {
  const [, setSearchParams] = useSearchParams()

  const [nodes, setNodes] = useState<SymbolRef[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [center, setCenter] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState(!focusSymbol)

  const [query, setQuery] = useState(focusSymbol)
  const [suggestions, setSuggestions] = useState<SymbolRef[]>([])

  useEffect(() => {
    let cancelled = false

    async function load() {
      if (focusSymbol) {
        const res: SubgraphResponse = await getSubgraph(focusSymbol, depth)
        if (cancelled) return
        setNodes(res.nodes)
        setEdges(res.edges)
        setCenter(res.center)
      } else {
        const res: GraphResponse = await getGraphOverview()
        if (cancelled) return
        setNodes(res.nodes)
        setEdges(res.edges)
        setCenter(undefined)
        setOverview(true)
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

  async function loadFullGraph() {
    setLoading(true)
    setError(null)
    try {
      const res = await getGraph()
      setNodes(res.nodes)
      setEdges(res.edges)
      setOverview(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "failed to load graph")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!query || query === focusSymbol) return
    let cancelled = false
    search(query).then((r) => {
      if (!cancelled) setSuggestions(r.slice(0, 8))
    })
    return () => {
      cancelled = true
    }
  }, [query, focusSymbol])

  const visibleSuggestions = query && query !== focusSymbol ? suggestions : []

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
          {visibleSuggestions.length > 0 && (
            <div className="graph-focus-suggestions">
              {visibleSuggestions.map((s) => (
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
        {!focusSymbol && overview && (
          <button type="button" className="graph-load-full" onClick={loadFullGraph}>
            Load full graph
          </button>
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
