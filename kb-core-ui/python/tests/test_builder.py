"""Port of internal/graph/builder_test.go."""

from __future__ import annotations

from kb_core_ui.builder import build
from kb_core_ui.models import (
    EDGE_CALLS,
    EDGE_CONTAINS,
    KIND_CLASS,
    KIND_FUNCTION,
    KIND_METHOD,
    FileGraph,
    Symbol,
    UnresolvedCall,
)


def sym(symbol_id: str, name: str, kind: str, **kw) -> Symbol:
    return Symbol(id=symbol_id, name=name, kind=kind, **kw)


def edge_tuples(g) -> set[tuple[str, str, str]]:
    return {(e.source, e.target, e.kind) for e in g.edges}


def targets_from(g, source: str) -> set[str]:
    return {e.target for e in g.edges if e.source == source}


def test_build_resolves_calls_and_contains():
    g = build(
        [
            FileGraph(
                file_path="a.go",
                language="",
                symbols=[
                    sym("a.go:Caller", "Caller", KIND_FUNCTION),
                    sym("a.go:Server", "Server", KIND_CLASS),
                    sym("a.go:Server.Start", "Start", KIND_METHOD, parent_id="a.go:Server"),
                ],
                unresolved_calls=[UnresolvedCall("a.go:Caller", "Helper", EDGE_CALLS)],
            ),
            FileGraph(
                file_path="b.go",
                language="",
                symbols=[sym("b.go:Helper", "Helper", KIND_FUNCTION)],
            ),
        ]
    )

    assert len(g.symbols) == 4
    assert ("a.go:Caller", "b.go:Helper", EDGE_CALLS) in edge_tuples(g)
    assert ("a.go:Server", "a.go:Server.Start", EDGE_CONTAINS) in edge_tuples(g)


def test_resolve_parents_across_files_in_same_package():
    """A Go type's methods routinely live in other files of the same package.
    The parser guesses a same-file parent (queries.go:Store) while the type is
    in store.go, so build_flat must repoint by (directory, receiver)."""
    g = build(
        [
            FileGraph(
                file_path="pkg/store.go",
                language="go",
                symbols=[
                    sym("pkg/store.go:Store", "Store", KIND_CLASS,
                        file_path="pkg/store.go", language="go"),
                    sym("pkg/store.go:Store.Open", "Open", KIND_METHOD,
                        file_path="pkg/store.go", receiver="Store",
                        parent_id="pkg/store.go:Store", language="go"),
                ],
            ),
            FileGraph(
                file_path="pkg/queries.go",
                language="go",
                symbols=[
                    sym("pkg/queries.go:Store.Search", "Search", KIND_METHOD,
                        file_path="pkg/queries.go", receiver="Store",
                        parent_id="pkg/queries.go:Store", language="go"),
                ],
            ),
        ]
    )

    assert g.symbols["pkg/queries.go:Store.Search"].parent_id == "pkg/store.go:Store"

    for e in g.edges:
        assert e.source in g.symbols, f"dangling edge source {e.source}"
        assert e.target in g.symbols, f"dangling edge target {e.target}"

    contained = {
        e.target
        for e in g.edges
        if e.kind == EDGE_CONTAINS and e.source == "pkg/store.go:Store"
    }
    assert contained == {"pkg/store.go:Store.Open", "pkg/queries.go:Store.Search"}


def test_qualified_call_never_uses_repo_wide_fallback():
    """"resp.Body.Close()" reduces to the bare name "Close"; the receiver is an
    unparsed stdlib type. A lone local "Close" must not absorb that call."""
    g = build(
        [
            FileGraph(
                file_path="a.go",
                language="go",
                symbols=[sym("a.go:DoRequest", "DoRequest", KIND_FUNCTION,
                             file_path="a.go", language="go")],
                unresolved_calls=[
                    UnresolvedCall("a.go:DoRequest", "Close", EDGE_CALLS, qualified=True)
                ],
            ),
            FileGraph(
                file_path="store/store.go",
                language="go",
                symbols=[sym("store/store.go:Close", "Close", KIND_METHOD,
                             file_path="store/store.go", language="go")],
            ),
        ]
    )
    assert targets_from(g, "a.go:DoRequest") == set()


def test_call_never_crosses_language_families():
    """Go's "os.Stat(...)" reduces to "Stat", colliding with a React "Stat"
    component. The unique-match fallback must not wire them together."""
    g = build(
        [
            FileGraph(
                file_path="cmd/common.go",
                language="go",
                symbols=[sym("cmd/common.go:resolveRepoPath", "resolveRepoPath",
                             KIND_FUNCTION, language="go")],
                unresolved_calls=[
                    UnresolvedCall("cmd/common.go:resolveRepoPath", "Stat", EDGE_CALLS)
                ],
            ),
            FileGraph(
                file_path="web/src/components/Header/Header.tsx",
                language="tsx",
                symbols=[sym("web/src/components/Header/Header.tsx:Stat", "Stat",
                             KIND_FUNCTION, language="tsx")],
            ),
        ]
    )
    assert targets_from(g, "cmd/common.go:resolveRepoPath") == set()


def test_call_matches_across_js_family():
    g = build(
        [
            FileGraph(
                file_path="web/src/App.tsx",
                language="tsx",
                symbols=[sym("web/src/App.tsx:App", "App", KIND_FUNCTION, language="tsx")],
                unresolved_calls=[UnresolvedCall("web/src/App.tsx:App", "helper", EDGE_CALLS)],
            ),
            FileGraph(
                file_path="web/src/utils/helper.ts",
                language="typescript",
                symbols=[sym("web/src/utils/helper.ts:helper", "helper",
                             KIND_FUNCTION, language="typescript")],
            ),
        ]
    )
    assert targets_from(g, "web/src/App.tsx:App") == {"web/src/utils/helper.ts:helper"}


def test_call_prefers_same_file_then_same_dir():
    g = build(
        [
            FileGraph(
                file_path="pkg/a.go",
                language="",
                symbols=[
                    sym("pkg/a.go:Caller", "Caller", KIND_FUNCTION, file_path="pkg/a.go"),
                    sym("pkg/a.go:log", "log", KIND_FUNCTION, file_path="pkg/a.go"),
                ],
                unresolved_calls=[UnresolvedCall("pkg/a.go:Caller", "log", EDGE_CALLS)],
            ),
            FileGraph(
                file_path="pkg/b.go",
                language="",
                symbols=[sym("pkg/b.go:log", "log", KIND_FUNCTION, file_path="pkg/b.go")],
            ),
            FileGraph(
                file_path="other/c.go",
                language="",
                symbols=[sym("other/c.go:log", "log", KIND_FUNCTION, file_path="other/c.go")],
            ),
        ]
    )
    assert targets_from(g, "pkg/a.go:Caller") == {"pkg/a.go:log"}
