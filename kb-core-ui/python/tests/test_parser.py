"""Port of internal/parser/parser_test.go."""

from __future__ import annotations

import pytest

from kb_core_ui.errors import ParserError
from kb_core_ui.models import (
    EDGE_HANDLES,
    KIND_CONST,
    KIND_FUNCTION,
    KIND_METHOD,
    KIND_ROUTE,
    KIND_VARIABLE,
    FileGraph,
)
from kb_core_ui.parser import parse_file
from kb_core_ui.parser.golang import parse_go
from kb_core_ui.parser.jslang import parse_typescript
from kb_core_ui.parser.pylang import parse_python


def find_sym(fg: FileGraph, symbol_id: str):
    for s in fg.symbols:
        if s.id == symbol_id:
            return s
    pytest.fail(f"symbol {symbol_id!r} not found; have: {[s.id for s in fg.symbols]}")


def calls(fg: FileGraph) -> set[tuple[str, str]]:
    return {(c.from_id, c.target_name) for c in fg.unresolved_calls}


GO_SRC = b"""package main

// Add returns the sum of a and b.
func Add(a int, b int) int {
\treturn helper(a) + b
}

type Server struct {
\tName string
}

// Start begins serving on port.
func (s *Server) Start(port int) error {
\tAdd(1, 2)
\ts.log(port)
\treturn nil
}

const MaxRetries = 3

var counter int = 0
"""


def test_parse_go():
    fg = parse_go("server.go", GO_SRC)

    add = find_sym(fg, "server.go:Add")
    assert add.kind == KIND_FUNCTION
    assert len(add.params) == 2
    assert add.doc

    start = find_sym(fg, "server.go:Server.Start")
    assert start.kind == KIND_METHOD
    assert start.receiver == "Server"

    for sym_id in ("server.go:Server", "server.go:MaxRetries", "server.go:counter"):
        find_sym(fg, sym_id)

    assert ("server.go:Add", "helper") in calls(fg)
    assert ("server.go:Server.Start", "log") in calls(fg)


GO_ROUTES_SRC = b"""package main

type Server struct{}

func (s *Server) routes(mux *http.ServeMux) {
\tmux.HandleFunc("GET /api/tree", s.handleTree)
\tmux.HandleFunc("POST /api/reindex", reindex)
}

func (s *Server) handleTree() {}

func reindex() {}
"""


def test_parse_go_routes():
    fg = parse_go("server.go", GO_ROUTES_SRC)

    routes = [s for s in fg.symbols if s.kind == KIND_ROUTE]
    assert {r.name for r in routes} == {"GET /api/tree", "POST /api/reindex"}

    handles = {
        (c.target_name, c.qualified)
        for c in fg.unresolved_calls
        if c.kind == EDGE_HANDLES
    }
    assert ("handleTree", True) in handles
    assert ("reindex", False) in handles


TS_SRC = b"""
/** Adds two numbers. */
export function add(a: number, b: number): number {
  return helper(a) + b;
}

export class Server {
  name: string;

  start(port: number): void {
    add(1, 2);
    this.log(port);
  }
}

export interface Handler {
  handle(req: string): string;
}

export const maxRetries: number = 3;
"""


def test_parse_typescript():
    fg = parse_typescript("server.ts", TS_SRC)

    add = find_sym(fg, "server.ts:add")
    assert add.kind == KIND_FUNCTION
    assert len(add.params) == 2
    assert add.params[0].type == "number"

    start = find_sym(fg, "server.ts:Server.start")
    assert start.kind == KIND_METHOD
    assert start.receiver == "Server"

    assert find_sym(fg, "server.ts:Handler.handle").kind == KIND_METHOD
    assert find_sym(fg, "server.ts:maxRetries").kind == KIND_CONST

    assert ("server.ts:add", "helper") in calls(fg)
    assert ("server.ts:Server.start", "log") in calls(fg)


PY_SRC = b'''
def add(a: int, b: int) -> int:
    """Adds two numbers."""
    return helper(a) + b


class Server:
    """A server."""

    def start(self, port: int) -> None:
        add(1, 2)
        self.log(port)


MAX_RETRIES = 3
counter = 0
'''


def test_parse_python():
    fg = parse_python("server.py", PY_SRC)

    add = find_sym(fg, "server.py:add")
    assert add.kind == KIND_FUNCTION
    assert len(add.params) == 2
    assert add.doc

    start = find_sym(fg, "server.py:Server.start")
    assert start.kind == KIND_METHOD
    assert start.receiver == "Server"
    assert len(start.params) == 1, "self should be dropped"

    assert find_sym(fg, "server.py:MAX_RETRIES").kind == KIND_CONST
    assert find_sym(fg, "server.py:counter").kind == KIND_VARIABLE

    assert ("server.py:add", "helper") in calls(fg)
    assert ("server.py:Server.start", "log") in calls(fg)


DOC_SRC = b"""package p

const (
\t// doc for A
\tA = 1
\tB = 2 // trailing for B
\tC = 3
)
"""


def test_trailing_comment_is_not_next_symbols_doc():
    fg = parse_go("p.go", DOC_SRC)
    assert find_sym(fg, "p.go:A").doc == "doc for A"
    assert find_sym(fg, "p.go:B").doc == ""
    assert find_sym(fg, "p.go:C").doc == ""


def test_parse_file_rejects_unknown_extension():
    with pytest.raises(ParserError):
        parse_file("notes.txt", b"")
