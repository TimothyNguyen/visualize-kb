import { useEffect, useState } from "react"
import type { SourceResponse } from "../../api/types"
import { getSource } from "../../api/client"
import "./CodePanel.css"

export function CodePanel({ filePath, start, end }: { filePath: string; start: number; end: number }) {
  return <CodePanelContent key={`${filePath}:${start}:${end}`} filePath={filePath} start={start} end={end} />
}

function CodePanelContent({ filePath, start, end }: { filePath: string; start: number; end: number }) {
  const [source, setSource] = useState<SourceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSource(filePath, start, end)
      .then((s) => {
        if (!cancelled) setSource(s)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load source")
      })
    return () => {
      cancelled = true
    }
  }, [filePath, start, end])

  return (
    <div className="code-panel">
      <div className="code-panel-header">
        <span className="code-panel-path">{filePath}</span>
        <span className="code-panel-range">
          L{start}–{end}
        </span>
      </div>
      {error && <div className="code-panel-error">{error}</div>}
      {!source && !error && <div className="code-panel-loading">Loading source…</div>}
      {source && (
        <pre className="code-panel-body">
          <code>
            {source.lines.map((line, i) => (
              <div className="code-line" key={source.startLine + i}>
                <span className="code-line-number">{source.startLine + i}</span>
                <span className="code-line-text">{line || " "}</span>
              </div>
            ))}
          </code>
        </pre>
      )}
    </div>
  )
}
