package parser

import (
	"testing"

	"kb-core-ui/internal/graph"
)

func findSym(t *testing.T, fg *graph.FileGraph, id string) graph.Symbol {
	t.Helper()
	for _, s := range fg.Symbols {
		if s.ID == id {
			return s
		}
	}
	t.Fatalf("symbol %q not found; have: %v", id, symbolIDs(fg))
	return graph.Symbol{}
}

func symbolIDs(fg *graph.FileGraph) []string {
	var ids []string
	for _, s := range fg.Symbols {
		ids = append(ids, s.ID)
	}
	return ids
}

func TestParseGo(t *testing.T) {
	src := []byte(`package main

// Add returns the sum of a and b.
func Add(a int, b int) int {
	return helper(a) + b
}

type Server struct {
	Name string
}

// Start begins serving on port.
func (s *Server) Start(port int) error {
	Add(1, 2)
	s.log(port)
	return nil
}

const MaxRetries = 3

var counter int = 0
`)
	fg, err := ParseGo("server.go", src)
	if err != nil {
		t.Fatal(err)
	}

	add := findSym(t, fg, "server.go:Add")
	if add.Kind != graph.KindFunction || len(add.Params) != 2 || add.Doc == "" {
		t.Fatalf("Add symbol wrong: %+v", add)
	}

	start := findSym(t, fg, "server.go:Server.Start")
	if start.Kind != graph.KindMethod || start.Receiver != "Server" {
		t.Fatalf("Start symbol wrong: %+v", start)
	}

	_ = findSym(t, fg, "server.go:Server")
	_ = findSym(t, fg, "server.go:MaxRetries")
	_ = findSym(t, fg, "server.go:counter")

	var gotAddCall, gotSelectorCall bool
	for _, c := range fg.UnresolvedCalls {
		if c.FromID == "server.go:Add" && c.TargetName == "helper" {
			gotAddCall = true
		}
		if c.FromID == "server.go:Server.Start" && c.TargetName == "log" {
			gotSelectorCall = true
		}
	}
	if !gotAddCall {
		t.Error("expected Add -> helper call")
	}
	if !gotSelectorCall {
		t.Error("expected Start -> log call")
	}
}

func TestParseGoRoutes(t *testing.T) {
	src := []byte(`package main

type Server struct{}

func (s *Server) routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/tree", s.handleTree)
	mux.HandleFunc("POST /api/reindex", reindex)
}

func (s *Server) handleTree() {}

func reindex() {}
`)
	fg, err := ParseGo("server.go", src)
	if err != nil {
		t.Fatal(err)
	}

	var routes []graph.Symbol
	for _, s := range fg.Symbols {
		if s.Kind == graph.KindRoute {
			routes = append(routes, s)
		}
	}
	if len(routes) != 2 {
		t.Fatalf("expected 2 route symbols, got %d: %+v", len(routes), routes)
	}

	names := map[string]bool{}
	for _, r := range routes {
		names[r.Name] = true
	}
	if !names["GET /api/tree"] || !names["POST /api/reindex"] {
		t.Fatalf("unexpected route names: %+v", names)
	}

	var gotMethodHandler, gotFuncHandler bool
	for _, c := range fg.UnresolvedCalls {
		if c.Kind != graph.EdgeHandles {
			continue
		}
		if c.TargetName == "handleTree" && c.Qualified {
			gotMethodHandler = true
		}
		if c.TargetName == "reindex" && !c.Qualified {
			gotFuncHandler = true
		}
	}
	if !gotMethodHandler {
		t.Error("expected GET /api/tree route to link to method handler s.handleTree (qualified)")
	}
	if !gotFuncHandler {
		t.Error("expected POST /api/reindex route to link to bare function handler reindex")
	}
}

func TestParseTypeScript(t *testing.T) {
	src := []byte(`
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
`)
	fg, err := ParseTypeScript("server.ts", src)
	if err != nil {
		t.Fatal(err)
	}

	add := findSym(t, fg, "server.ts:add")
	if add.Kind != graph.KindFunction || len(add.Params) != 2 || add.Params[0].Type != "number" {
		t.Fatalf("add symbol wrong: %+v", add)
	}

	start := findSym(t, fg, "server.ts:Server.start")
	if start.Kind != graph.KindMethod || start.Receiver != "Server" {
		t.Fatalf("start symbol wrong: %+v", start)
	}

	handle := findSym(t, fg, "server.ts:Handler.handle")
	if handle.Kind != graph.KindMethod {
		t.Fatalf("handle symbol wrong: %+v", handle)
	}

	mr := findSym(t, fg, "server.ts:maxRetries")
	if mr.Kind != graph.KindConst {
		t.Fatalf("maxRetries wrong kind: %+v", mr)
	}

	var gotCall, gotMemberCall bool
	for _, c := range fg.UnresolvedCalls {
		if c.FromID == "server.ts:add" && c.TargetName == "helper" {
			gotCall = true
		}
		if c.FromID == "server.ts:Server.start" && c.TargetName == "log" {
			gotMemberCall = true
		}
	}
	if !gotCall || !gotMemberCall {
		t.Errorf("missing calls: gotCall=%v gotMemberCall=%v edges=%+v", gotCall, gotMemberCall, fg.UnresolvedCalls)
	}
}

func TestParsePython(t *testing.T) {
	src := []byte(`
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
`)
	fg, err := ParsePython("server.py", src)
	if err != nil {
		t.Fatal(err)
	}

	add := findSym(t, fg, "server.py:add")
	if add.Kind != graph.KindFunction || len(add.Params) != 2 || add.Doc == "" {
		t.Fatalf("add symbol wrong: %+v", add)
	}

	start := findSym(t, fg, "server.py:Server.start")
	if start.Kind != graph.KindMethod || start.Receiver != "Server" || len(start.Params) != 1 {
		t.Fatalf("start symbol wrong (self should be dropped): %+v", start)
	}

	mr := findSym(t, fg, "server.py:MAX_RETRIES")
	if mr.Kind != graph.KindConst {
		t.Fatalf("MAX_RETRIES wrong kind: %+v", mr)
	}
	cnt := findSym(t, fg, "server.py:counter")
	if cnt.Kind != graph.KindVariable {
		t.Fatalf("counter wrong kind: %+v", cnt)
	}

	var gotCall, gotMemberCall bool
	for _, c := range fg.UnresolvedCalls {
		if c.FromID == "server.py:add" && c.TargetName == "helper" {
			gotCall = true
		}
		if c.FromID == "server.py:Server.start" && c.TargetName == "log" {
			gotMemberCall = true
		}
	}
	if !gotCall || !gotMemberCall {
		t.Errorf("missing calls: gotCall=%v gotMemberCall=%v edges=%+v", gotCall, gotMemberCall, fg.UnresolvedCalls)
	}
}
