"""Port of internal/store/store_test.go and internal/indexer/indexer_test.go."""

from __future__ import annotations

import os

import pytest

from kb_core_ui.indexer import index
from kb_core_ui.parser.golang import parse_go
from kb_core_ui.parser.jslang import parse_typescript
from kb_core_ui.parser.pylang import parse_python
from kb_core_ui.store import Store


@pytest.fixture
def store(tmp_path):
    with Store(str(tmp_path / "graph.db")) as s:
        yield s


def test_ingest_and_query(store):
    # Same language but different files, so Calls/Callers exercise a real
    # cross-file resolved edge rather than a same-file one.
    store.upsert_file(
        parse_go("a.go", b"package main\n\nfunc Add(a int, b int) int {\n\treturn helper(a, b)\n}\n"),
        "hash1",
    )
    store.upsert_file(
        parse_go("b.go", b"package main\n\nfunc helper(a int, b int) int {\n\treturn a + b\n}\n"),
        "hash2",
    )
    store.rebuild_edges()

    assert len(store.tree().children) == 2

    syms = store.symbols_in_file("a.go")
    assert [s.name for s in syms] == ["Add"]

    add_id = syms[0].id
    assert len(store.symbol(add_id).params) == 2

    calls = store.calls(add_id)
    assert [c.symbol.name for c in calls] == ["helper"]

    callers = store.callers(calls[0].symbol.id)
    assert [c.symbol.id for c in callers] == [add_id]

    nodes, edges = store.full_graph()
    assert (len(nodes), len(edges)) == (2, 1)

    assert [r.id for r in store.search("add", "")] == [add_id]

    stats = store.stats()
    assert (stats.files, stats.symbols, stats.edges) == (2, 2, 1)


def test_upsert_file_replaces_previous_content(store):
    store.upsert_file(parse_go("a.go", b"package main\nfunc One() {}\n"), "h1")
    store.upsert_file(parse_go("a.go", b"package main\nfunc Two() {}\n"), "h2")

    assert [s.name for s in store.symbols_in_file("a.go")] == ["Two"]
    assert store.file_hash("a.go") == ("h2", True)


def test_upsert_file_keeps_last_same_file_definition(store):
    graph = parse_python("a.py", b"def duplicate():\n    return 1\n\ndef duplicate():\n    return 2\n")

    store.upsert_file(graph, "h1")

    symbols = store.symbols_in_file("a.py")
    assert len(symbols) == 1
    assert symbols[0].start_line == 4


def test_symbol_with_no_params_or_returns_is_never_none(store):
    """"func main()" has zero params and zero returns, which round-trips
    through SQLite as JSON "null". Symbol() must normalize that back to [] —
    API_CONTRACT.md documents [] as the empty case and the frontend .map()s
    over it unconditionally."""
    store.upsert_file(
        parse_go("main.go", b"package main\n\nfunc main() {\n\thelper()\n}\n"), "hash1"
    )

    sym = store.symbol("main.go:main")
    assert sym.params == []
    assert sym.returns == []


def test_symbol_absent_returns_none(store):
    assert store.symbol("nope.go:Nope") is None


def test_stored_json_uses_go_html_escaping(store):
    """Go's encoding/json escapes < > & by default, so a generic return type
    is stored differently than json.dumps would write it."""
    store.upsert_file(parse_typescript("a.ts", b"export function f(): Promise<number> {}\n"), "h")
    row = store.db.execute("SELECT returns_json FROM symbols WHERE id = 'a.ts:f'").fetchone()
    assert row[0] == '[{"name":"","type":"Promise\\u003cnumber\\u003e"}]'


def write(path, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def test_index_scan_reparse_and_prune(store, tmp_path):
    repo = tmp_path / "repo"
    write(str(repo / "a.go"), "package main\nfunc Add(a, b int) int { return helper(a, b) }\n")
    write(str(repo / "b.go"), "package main\nfunc helper(a, b int) int { return a + b }\n")
    write(str(repo / "node_modules" / "skip.js"), "function skip() {}\n")
    write(str(repo / ".venv-ui" / "skip.py"), "def skip(): pass\n")
    write(str(repo / ".worktrees" / "baseline" / "skip.go"), "package skip\nfunc Skip() {}\n")

    res = index(str(repo), store)
    assert res.files_changed == 2, "dependency and virtualenv directories should be skipped"

    stats = store.stats()
    assert (stats.symbols, stats.edges) == (2, 1)

    assert index(str(repo), store).files_changed == 0

    os.remove(repo / "b.go")
    assert index(str(repo), store).files_removed == 1
    assert store.symbols_in_file("b.go") == []
