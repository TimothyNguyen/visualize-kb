"""Persists a parsed repo's symbols, calls and resolved edges in SQLite —
the Python side of internal/store/store.go and queries.go.

Schema text is copied verbatim so an existing .kb-core-ui/graph.db written by
the Go binary opens unchanged, and vice versa.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from kb_core_ui import jsonx
from kb_core_ui.builder import base_of, build_flat, dir_of
from kb_core_ui.errors import StoreError
from kb_core_ui.models import Edge, FileGraph, Param, Symbol, SymbolRef, TreeNode, UnresolvedCall

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
	path TEXT PRIMARY KEY,
	hash TEXT NOT NULL,
	language TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
	id TEXT PRIMARY KEY,
	file_path TEXT NOT NULL,
	name TEXT NOT NULL,
	kind TEXT NOT NULL,
	start_line INTEGER NOT NULL,
	end_line INTEGER NOT NULL,
	signature TEXT NOT NULL,
	params_json TEXT NOT NULL,
	returns_json TEXT NOT NULL,
	receiver TEXT NOT NULL,
	parent_id TEXT NOT NULL,
	language TEXT NOT NULL,
	doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_id);

CREATE TABLE IF NOT EXISTS unresolved_calls (
	file_path TEXT NOT NULL,
	from_id TEXT NOT NULL,
	target_name TEXT NOT NULL,
	kind TEXT NOT NULL,
	qualified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calls_file ON unresolved_calls(file_path);

CREATE TABLE IF NOT EXISTS edges (
	source TEXT NOT NULL,
	target TEXT NOT NULL,
	kind TEXT NOT NULL,
	PRIMARY KEY (source, target, kind)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
"""

_SYMBOL_COLUMNS = (
    "id, file_path, name, kind, start_line, end_line, signature, "
    "params_json, returns_json, receiver, parent_id, language, doc"
)
_REF_COLUMNS = "id, name, kind, file_path, start_line, end_line"


@dataclass
class EdgeWithSymbol:
    edge: Edge
    symbol: SymbolRef

    def to_json_dict(self) -> dict:
        return {"edge": self.edge.to_json_dict(), "symbol": self.symbol.to_json_dict()}


@dataclass
class Stats:
    files: int = 0
    symbols: int = 0
    edges: int = 0
    languages: dict[str, int] = field(default_factory=dict)


@dataclass
class FileCount:
    path: str
    count: int


@dataclass
class Health:
    files: int = 0
    symbols: int = 0
    edges: int = 0
    unresolved_calls: int = 0
    resolved_calls: int = 0
    resolution_rate: float = 0.0
    dangling_edges: int = 0
    top_unresolved_files: list[FileCount] = field(default_factory=list)


def _params(raw: str) -> list[Param]:
    # "null" (a zero-param symbol) decodes to None, which would re-encode to
    # the API as `null`; API_CONTRACT.md documents [] as the empty case and
    # the frontend calls .map() unconditionally.
    decoded = jsonx.loads(raw)
    return [Param(name=p["name"], type=p["type"]) for p in decoded] if decoded else []


def _scan_symbol(row) -> Symbol:
    return Symbol(
        id=row[0],
        file_path=row[1],
        name=row[2],
        kind=row[3],
        start_line=row[4],
        end_line=row[5],
        signature=row[6],
        params=_params(row[7]),
        returns=_params(row[8]),
        receiver=row[9],
        parent_id=row[10],
        language=row[11],
        doc=row[12],
    )


def _scan_ref(row) -> SymbolRef:
    return SymbolRef(
        id=row[0], name=row[1], kind=row[2], file_path=row[3], start_line=row[4], end_line=row[5]
    )


class Store:
    def __init__(self, path: str):
        try:
            # check_same_thread=False: `serve` dispatches each request on
            # its own thread, mirroring Go's goroutine-per-connection
            # server. Concurrent use is serialized by the REST layer's
            # lock (server/app.py), not by sqlite3's thread check.
            self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        except sqlite3.Error as exc:
            raise StoreError(f"store: open {path}: {exc}") from None
        try:
            self.db.executescript(SCHEMA)
        except sqlite3.Error as exc:
            self.db.close()
            raise StoreError(f"store: apply schema: {exc}") from None
        try:
            self._migrate()
        except sqlite3.Error as exc:
            self.db.close()
            raise StoreError(f"store: migrate: {exc}") from None

    def _migrate(self) -> None:
        """CREATE TABLE IF NOT EXISTS is a no-op against an existing file, so
        columns added later need an explicit ALTER. The cache is rebuildable
        from source, so existing rows just take the default."""
        names = {r[0] for r in self.db.execute("SELECT name FROM pragma_table_info('unresolved_calls')")}
        if "qualified" not in names:
            self.db.execute(
                "ALTER TABLE unresolved_calls ADD COLUMN qualified INTEGER NOT NULL DEFAULT 0"
            )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- indexing ----------------------------------------------------

    def file_hash(self, path: str) -> tuple[str, bool]:
        row = self.db.execute("SELECT hash FROM files WHERE path = ?", (path,)).fetchone()
        return (row[0], True) if row else ("", False)

    def known_files(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT path FROM files")]

    def upsert_file(self, fg: FileGraph, content_hash: str) -> None:
        """Replaces one file's symbols and calls. Call rebuild_edges once
        after a batch of these — resolution needs the whole repo."""
        with self.db:
            self.db.execute("BEGIN")
            self._delete_file(fg.file_path)
            self.db.execute(
                "INSERT INTO files(path, hash, language) VALUES (?, ?, ?)",
                (fg.file_path, content_hash, fg.language),
            )
            self.db.executemany(
                f"INSERT INTO symbols ({_SYMBOL_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        s.id, s.file_path, s.name, s.kind, s.start_line, s.end_line, s.signature,
                        jsonx.dumps(None if s.params is None else [p.to_json_dict() for p in s.params]),
                        jsonx.dumps(None if s.returns is None else [p.to_json_dict() for p in s.returns]),
                        s.receiver, s.parent_id, s.language, s.doc,
                    )
                    for s in fg.symbols
                ],
            )
            self.db.executemany(
                "INSERT INTO unresolved_calls(file_path, from_id, target_name, kind, qualified) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (fg.file_path, c.from_id, c.target_name, c.kind, int(c.qualified))
                    for c in fg.unresolved_calls
                ],
            )

    def remove_file(self, path: str) -> None:
        with self.db:
            self.db.execute("BEGIN")
            self._delete_file(path)

    def _delete_file(self, path: str) -> None:
        self.db.execute("DELETE FROM files WHERE path = ?", (path,))
        self.db.execute("DELETE FROM symbols WHERE file_path = ?", (path,))
        self.db.execute("DELETE FROM unresolved_calls WHERE file_path = ?", (path,))

    def rebuild_edges(self) -> None:
        symbols = [_scan_symbol(r) for r in self.db.execute(f"SELECT {_SYMBOL_COLUMNS} FROM symbols")]
        calls = [
            UnresolvedCall(from_id=r[0], target_name=r[1], kind=r[2], qualified=bool(r[3]))
            for r in self.db.execute("SELECT from_id, target_name, kind, qualified FROM unresolved_calls")
        ]
        g = build_flat(symbols, calls)

        with self.db:
            self.db.execute("BEGIN")
            # Persist parent_ids build_flat corrected (a method whose type
            # lives in another file of the same package), so Members and
            # SymbolsInFile — which read parent_id straight from this table —
            # agree with the edges written below.
            self.db.executemany(
                "UPDATE symbols SET parent_id = ? WHERE id = ?",
                [
                    (g.symbols[s.id].parent_id, s.id)
                    for s in symbols
                    if g.symbols[s.id].parent_id != s.parent_id
                ],
            )
            self.db.execute("DELETE FROM edges")
            self.db.executemany(
                "INSERT OR IGNORE INTO edges(source, target, kind) VALUES (?, ?, ?)",
                [(e.source, e.target, e.kind) for e in g.edges],
            )

    # ---- queries -----------------------------------------------------

    def tree(self) -> TreeNode:
        root = TreeNode(path="", name="", type="dir", children=[])
        dirs: dict[str, TreeNode] = {"": root}

        def ensure_dir(path: str) -> TreeNode:
            existing = dirs.get(path)
            if existing is not None:
                return existing
            node = TreeNode(path=path, name=base_of(path), type="dir", children=[])
            ensure_dir(dir_of(path)).children.append(node)
            dirs[path] = node
            return node

        for path, lang in self.db.execute("SELECT path, language FROM files ORDER BY path"):
            ensure_dir(dir_of(path)).children.append(
                TreeNode(path=path, name=base_of(path), type="file", language=lang)
            )
        return root

    def symbols_in_file(self, path: str) -> list[SymbolRef]:
        return [
            _scan_ref(r)
            for r in self.db.execute(
                f"SELECT {_REF_COLUMNS} FROM symbols "
                "WHERE file_path = ? AND parent_id = '' ORDER BY start_line",
                (path,),
            )
        ]

    def symbol(self, symbol_id: str) -> Symbol | None:
        row = self.db.execute(
            f"SELECT {_SYMBOL_COLUMNS} FROM symbols WHERE id = ?", (symbol_id,)
        ).fetchone()
        return _scan_symbol(row) if row else None

    def members(self, symbol_id: str) -> list[SymbolRef]:
        return [
            _scan_ref(r)
            for r in self.db.execute(
                f"SELECT {_REF_COLUMNS} FROM symbols WHERE parent_id = ? ORDER BY start_line",
                (symbol_id,),
            )
        ]

    def calls(self, symbol_id: str) -> list[EdgeWithSymbol]:
        return self._edges_joined(
            "SELECT e.source, e.target, e.kind, s.id, s.name, s.kind, s.file_path, s.start_line, s.end_line "
            "FROM edges e JOIN symbols s ON s.id = e.target WHERE e.source = ?",
            symbol_id,
        )

    def callers(self, symbol_id: str) -> list[EdgeWithSymbol]:
        return self._edges_joined(
            "SELECT e.source, e.target, e.kind, s.id, s.name, s.kind, s.file_path, s.start_line, s.end_line "
            "FROM edges e JOIN symbols s ON s.id = e.source WHERE e.target = ?",
            symbol_id,
        )

    def _edges_joined(self, query: str, symbol_id: str) -> list[EdgeWithSymbol]:
        return [
            EdgeWithSymbol(
                edge=Edge(source=r[0], target=r[1], kind=r[2]),
                symbol=SymbolRef(
                    id=r[3], name=r[4], kind=r[5], file_path=r[6], start_line=r[7], end_line=r[8]
                ),
            )
            for r in self.db.execute(query, (symbol_id,))
        ]

    def full_graph(self) -> tuple[list[SymbolRef], list[Edge]]:
        nodes = [_scan_ref(r) for r in self.db.execute(f"SELECT {_REF_COLUMNS} FROM symbols")]
        edges = [
            Edge(source=r[0], target=r[1], kind=r[2])
            for r in self.db.execute("SELECT source, target, kind FROM edges")
        ]
        return nodes, edges

    def subgraph(self, center: str, depth: int) -> tuple[list[SymbolRef], list[Edge]]:
        visited = {center}
        frontier = [center]
        edge_set: set[tuple[str, str, str]] = set()

        for _ in range(depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for symbol_id in frontier:
                for source, target, kind in self.db.execute(
                    "SELECT source, target, kind FROM edges WHERE source = ? OR target = ?",
                    (symbol_id, symbol_id),
                ).fetchall():
                    edge_set.add((source, target, kind))
                    other = source if target == symbol_id else target
                    if other not in visited:
                        visited.add(other)
                        next_frontier.append(other)
            frontier = next_frontier

        nodes: list[SymbolRef] = []
        for symbol_id in sorted(visited):
            row = self.db.execute(
                f"SELECT {_REF_COLUMNS} FROM symbols WHERE id = ?", (symbol_id,)
            ).fetchone()
            if row:
                nodes.append(_scan_ref(row))
        return nodes, [Edge(source=s, target=t, kind=k) for s, t, k in edge_set]

    def search(self, q: str, kind: str) -> list[SymbolRef]:
        query = f"SELECT {_REF_COLUMNS} FROM symbols WHERE name LIKE ?"
        args: list = [f"%{q}%"]
        if kind:
            query += " AND kind = ?"
            args.append(kind)
        query += " LIMIT 200"
        refs = [_scan_ref(r) for r in self.db.execute(query, args)]
        ql = q.lower()
        refs.sort(key=lambda r: _rank(r.name, ql))
        return refs

    def stats(self) -> Stats:
        st = Stats(
            files=self._count("SELECT COUNT(*) FROM files"),
            symbols=self._count("SELECT COUNT(*) FROM symbols"),
            edges=self._count("SELECT COUNT(*) FROM edges"),
        )
        for lang, n in self.db.execute("SELECT language, COUNT(*) FROM files GROUP BY language"):
            st.languages[lang] = n
        return st

    def health(self) -> Health:
        h = Health(
            files=self._count("SELECT COUNT(*) FROM files"),
            symbols=self._count("SELECT COUNT(*) FROM symbols"),
            edges=self._count("SELECT COUNT(*) FROM edges"),
            unresolved_calls=self._count("SELECT COUNT(*) FROM unresolved_calls"),
            # Only 'calls'/'handles' come from call sites; contains/implements/
            # extends are structural and don't count toward the rate.
            resolved_calls=self._count("SELECT COUNT(*) FROM edges WHERE kind IN ('calls','handles')"),
            dangling_edges=self._count(
                "SELECT COUNT(*) FROM edges e "
                "WHERE NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = e.source) "
                "   OR NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = e.target)"
            ),
        )
        total = h.resolved_calls + h.unresolved_calls
        if total > 0:
            h.resolution_rate = h.resolved_calls / total
        h.top_unresolved_files = [
            FileCount(path=r[0], count=r[1])
            for r in self.db.execute(
                "SELECT file_path, COUNT(*) AS n FROM unresolved_calls "
                "GROUP BY file_path ORDER BY n DESC LIMIT 5"
            )
        ]
        return h

    def _count(self, query: str) -> int:
        return self.db.execute(query).fetchone()[0]


def _rank(name: str, ql: str) -> int:
    nl = name.lower()
    if nl == ql:
        return 0
    if nl.startswith(ql):
        return 1
    return 2
