"""Merges per-file parse results into one repo-wide graph and resolves each
call site to a concrete edge — the Python side of internal/graph/builder.go.

Resolution is name-based, not type-directed: a call site only carries the
bare identifier written at it. Candidates are narrowed to the same language
family, then same file, then same directory, and only unqualified calls fall
back to a repo-wide unique match. Ambiguous names are left unresolved rather
than drawing a misleading edge.
"""

from __future__ import annotations

import dataclasses

from kb_core_ui.models import (
    EDGE_CONTAINS,
    KIND_CLASS,
    KIND_INTERFACE,
    Edge,
    FileGraph,
    Graph,
    Symbol,
    UnresolvedCall,
)


def dir_of(path: str) -> str:
    i = path.rfind("/")
    return path[:i] if i >= 0 else ""


def base_of(path: str) -> str:
    i = path.rfind("/")
    return path[i + 1 :] if i >= 0 else path


def language_family(lang: str) -> str:
    """TypeScript/TSX/JavaScript share one runtime and import across
    extensions. Go and Python never call into it or each other, so a
    same-named symbol there is a coincidence, not a call target."""
    if lang in ("typescript", "tsx", "javascript"):
        return "js"
    return lang


def build(files: list[FileGraph]) -> Graph:
    symbols: list[Symbol] = []
    calls: list[UnresolvedCall] = []
    for fg in files:
        symbols.extend(fg.symbols)
        calls.extend(fg.unresolved_calls)
    return build_flat(symbols, calls)


def build_flat(symbols: list[Symbol], calls: list[UnresolvedCall]) -> Graph:
    """Same resolution as build() but over flat rows, as the store persists
    them. Also corrects each member's parent_id: a parser guesses a method's
    parent in its own file, but a Go type's methods routinely live in other
    files of the same package. Callers that persist symbols should write back
    the corrected parent_ids from graph.symbols."""
    g = Graph()
    by_name: dict[str, list[Symbol]] = {}

    for sym in symbols:
        # Copied because _resolve_parents rewrites parent_id, and the caller's
        # originals are what RebuildEdges diffs the corrections against.
        g.symbols[sym.id] = dataclasses.replace(sym)
        by_name.setdefault(sym.name, []).append(sym)

    _resolve_parents(g)

    # Iterate the input slice, not the dict, so edge order is input order.
    # Skip parents that still don't resolve rather than dangling an edge.
    for original in symbols:
        sym = g.symbols[original.id]
        if not sym.parent_id:
            continue
        if sym.parent_id in g.symbols:
            g.edges.append(Edge(source=sym.parent_id, target=sym.id, kind=EDGE_CONTAINS))

    for call in calls:
        frm = g.symbols.get(call.from_id)
        if frm is None:
            continue
        target = _resolve_call(frm, call.target_name, call.qualified, by_name)
        if not target:
            continue
        g.edges.append(Edge(source=call.from_id, target=target, kind=call.kind))

    return g


def _resolve_parents(g: Graph) -> None:
    types_by_dir_name: dict[str, str] = {}
    for sym in g.symbols.values():
        if sym.kind in (KIND_CLASS, KIND_INTERFACE):
            types_by_dir_name[dir_of(sym.file_path) + "\x00" + sym.name] = sym.id

    for sym_id, sym in g.symbols.items():
        if not sym.parent_id or sym.parent_id in g.symbols or not sym.receiver:
            continue
        real_id = types_by_dir_name.get(dir_of(sym.file_path) + "\x00" + sym.receiver)
        if real_id and real_id != sym_id:
            sym.parent_id = real_id


def _resolve_call(
    frm: Symbol, name: str, qualified: bool, by_name: dict[str, list[Symbol]]
) -> str:
    family = language_family(frm.language)
    candidates = [c for c in by_name.get(name, []) if language_family(c.language) == family]
    if not candidates:
        return ""

    from_dir = dir_of(frm.file_path)
    same_dir: Symbol | None = None
    for c in candidates:
        if c.file_path == frm.file_path:
            return c.id
        if same_dir is None and dir_of(c.file_path) == from_dir:
            same_dir = c
    if same_dir is not None:
        return same_dir.id
    if not qualified and len(candidates) == 1:
        return candidates[0].id
    return ""
