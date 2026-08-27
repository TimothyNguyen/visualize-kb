import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react"
import { useNavigate } from "react-router-dom"
import type { SymbolRef } from "../../api/types"
import { search } from "../../api/client"
import { KindBadge } from "../Badges/Badges"
import "./CommandPalette.css"

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SymbolRef[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  // useLayoutEffect + a synchronous focus() call, not requestAnimationFrame:
  // rAF defers focus past the next paint, so keystrokes typed immediately
  // after the palette opens (a fast typist, or a script) land on whatever
  // element had focus before — not the palette's own input.
  useLayoutEffect(() => {
    if (open) {
      inputRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setQuery("")
      setResults([])
      setActiveIndex(0)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    search(query)
      .then((r) => {
        if (!cancelled) {
          setResults(r)
          setActiveIndex(0)
        }
      })
      .catch(() => {
        if (!cancelled) setResults([])
      })
    return () => {
      cancelled = true
    }
  }, [query, open])

  function select(symbol: SymbolRef) {
    navigate(`/symbol/${encodeURIComponent(symbol.id)}`)
    onClose()
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      onClose()
    } else if (e.key === "ArrowDown") {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      const chosen = results[activeIndex]
      if (chosen) select(chosen)
    }
  }

  if (!open) return null

  return (
    <div className="palette-overlay" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()} onKeyDown={onKeyDown}>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Search functions, classes, consts…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="palette-results scroll-y">
          {results.length === 0 && <div className="palette-empty">No matching symbols</div>}
          {results.map((r, i) => (
            <button
              type="button"
              key={r.id}
              className={`palette-row ${i === activeIndex ? "active" : ""}`}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => select(r)}
            >
              <KindBadge kind={r.kind} />
              <span className="palette-row-name">{r.name}</span>
              <span className="palette-row-path">{r.filePath}:{r.startLine}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
