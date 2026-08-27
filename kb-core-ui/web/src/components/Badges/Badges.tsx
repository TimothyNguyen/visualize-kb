import type { CSSProperties } from "react"
import type { SymbolKind } from "../../api/types"
import { KIND_LABEL, kindColor, languageIcon } from "../../utils/style"
import "./Badges.css"

export function KindBadge({ kind }: { kind: SymbolKind }) {
  return (
    <span className="badge kind-badge" style={{ "--badge-color": kindColor(kind) } as CSSProperties}>
      {KIND_LABEL[kind] ?? kind}
    </span>
  )
}

export function LanguageBadge({ language }: { language?: string }) {
  if (!language) return null
  return (
    <span className={`badge lang-badge lang-${language.toLowerCase()}`} title={language}>
      {languageIcon(language)}
    </span>
  )
}
