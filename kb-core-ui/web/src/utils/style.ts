import type { EdgeKind, SymbolKind } from "../api/types"

export const KIND_LABEL: Record<SymbolKind, string> = {
  module: "module",
  package: "package",
  class: "class",
  interface: "interface",
  function: "func",
  method: "method",
  const: "const",
  variable: "var",
  route: "route",
}

export const KIND_COLOR_VAR: Record<SymbolKind, string> = {
  module: "--k-module",
  package: "--k-package",
  class: "--k-class",
  interface: "--k-interface",
  function: "--k-function",
  method: "--k-method",
  const: "--k-const",
  variable: "--k-variable",
  route: "--k-route",
}

export const EDGE_LABEL: Record<EdgeKind, string> = {
  calls: "calls",
  references: "references",
  contains: "contains",
  implements: "implements",
  extends: "extends",
  handles: "handles",
}

export const EDGE_COLOR_VAR: Record<EdgeKind, string> = {
  calls: "--e-calls",
  references: "--e-references",
  contains: "--e-contains",
  implements: "--e-implements",
  extends: "--e-extends",
  handles: "--e-handles",
}

export function kindColor(kind: SymbolKind): string {
  return `var(${KIND_COLOR_VAR[kind] ?? "--k-module"})`
}

// Plain (non CSS-variable) hex values for contexts like the MiniMap canvas
// that can't resolve `var(...)` at draw time.
const KIND_HEX: Record<SymbolKind, string> = {
  module: "#8b93a5",
  package: "#8b93a5",
  class: "#f0946b",
  interface: "#c2a4ec",
  function: "#7c9dff",
  method: "#4fd6cd",
  const: "#f0cc6b",
  variable: "#a8de78",
  route: "#e07be0",
}

export function kindHexColor(kind: SymbolKind): string {
  return KIND_HEX[kind] ?? "#8b93a5"
}

export function edgeColor(kind: EdgeKind): string {
  return `var(${EDGE_COLOR_VAR[kind] ?? "--e-contains"})`
}

const LANGUAGE_ICON: Record<string, string> = {
  typescript: "TS",
  javascript: "JS",
  go: "Go",
  python: "Py",
}

export function languageIcon(language?: string): string {
  if (!language) return "?"
  return LANGUAGE_ICON[language.toLowerCase()] ?? language.slice(0, 2).toUpperCase()
}
