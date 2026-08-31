import { useEffect, useState } from "react"
import { NavLink } from "react-router-dom"
import type { StatsResponse } from "../../api/types"
import { getStats } from "../../api/client"
import "./Header.css"

export function Header({ onOpenSearch }: { onOpenSearch: () => void }) {
  const [stats, setStats] = useState<StatsResponse | null>(null)

  useEffect(() => {
    let cancelled = false
    getStats()
      .then((s) => {
        if (!cancelled) setStats(s)
      })
      .catch(() => {
        // stats are non-critical; fail silently in the header
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <header className="app-header">
      <div className="app-header-brand">
        <span className="brand-mark">◆</span>
        <span className="brand-name">KB Core UI</span>
      </div>

      <nav className="app-header-nav">
        <NavLink to="/graph" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Graph
        </NavLink>
        <NavLink to="/bots" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Bots
        </NavLink>
        <NavLink to="/memory" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Memory
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
          Chat
        </NavLink>
      </nav>

      <button type="button" className="search-trigger" onClick={onOpenSearch}>
        <span className="search-icon">⌕</span>
        <span>Search symbols…</span>
        <kbd>⌘K</kbd>
      </button>

      <div className="app-header-stats">
        {stats ? (
          <>
            <Stat label="files" value={stats.files} />
            <Stat label="symbols" value={stats.symbols} />
            <Stat label="edges" value={stats.edges} />
            <div className="lang-breakdown">
              {Object.entries(stats.languages).map(([lang, count]) => (
                <span key={lang} className="lang-stat" title={`${lang}: ${count}`}>
                  {lang} <b>{count}</b>
                </span>
              ))}
            </div>
          </>
        ) : (
          <span className="stats-loading">loading stats…</span>
        )}
      </div>
    </header>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}
