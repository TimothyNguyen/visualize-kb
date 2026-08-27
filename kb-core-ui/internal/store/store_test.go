package store

import (
	"path/filepath"
	"testing"

	"kb-core-ui/internal/parser"
)

func TestIngestAndQuery(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "graph.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	goSrcA := []byte(`package main

func Add(a int, b int) int {
	return helper(a, b)
}
`)
	// Same-language ("go") but a different file, so Calls/Callers exercise a
	// real cross-file resolved edge rather than a same-file one.
	goSrcB := []byte(`package main

func helper(a int, b int) int {
	return a + b
}
`)

	goFG, err := parser.ParseGo("a.go", goSrcA)
	if err != nil {
		t.Fatal(err)
	}
	goFG2, err := parser.ParseGo("b.go", goSrcB)
	if err != nil {
		t.Fatal(err)
	}

	if err := s.UpsertFile(goFG, "hash1"); err != nil {
		t.Fatal(err)
	}
	if err := s.UpsertFile(goFG2, "hash2"); err != nil {
		t.Fatal(err)
	}
	if err := s.RebuildEdges(); err != nil {
		t.Fatal(err)
	}

	tree, err := s.Tree()
	if err != nil {
		t.Fatal(err)
	}
	if len(tree.Children) != 2 {
		t.Fatalf("expected 2 top-level entries, got %d: %+v", len(tree.Children), tree)
	}

	syms, err := s.SymbolsInFile("a.go")
	if err != nil {
		t.Fatal(err)
	}
	if len(syms) != 1 || syms[0].Name != "Add" {
		t.Fatalf("unexpected symbols in a.go: %+v", syms)
	}

	addID := syms[0].ID
	sym, ok, err := s.Symbol(addID)
	if err != nil || !ok {
		t.Fatalf("Symbol(%s) failed: ok=%v err=%v", addID, ok, err)
	}
	if len(sym.Params) != 2 {
		t.Fatalf("expected 2 params, got %+v", sym.Params)
	}

	calls, err := s.Calls(addID)
	if err != nil {
		t.Fatal(err)
	}
	if len(calls) != 1 || calls[0].Symbol.Name != "helper" {
		t.Fatalf("expected Add -> helper edge, got %+v", calls)
	}

	callers, err := s.Callers(calls[0].Symbol.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(callers) != 1 || callers[0].Symbol.ID != addID {
		t.Fatalf("expected helper caller to be Add, got %+v", callers)
	}

	nodes, edges, err := s.FullGraph()
	if err != nil {
		t.Fatal(err)
	}
	if len(nodes) != 2 || len(edges) != 1 {
		t.Fatalf("expected 2 nodes / 1 edge, got %d/%d", len(nodes), len(edges))
	}

	results, err := s.Search("add", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || results[0].ID != addID {
		t.Fatalf("expected search to find Add, got %+v", results)
	}

	stats, err := s.Stats()
	if err != nil {
		t.Fatal(err)
	}
	if stats.Files != 2 || stats.Symbols != 2 || stats.Edges != 1 {
		t.Fatalf("unexpected stats: %+v", stats)
	}
}

func TestUpsertFileReplacesPreviousContent(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "graph.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	v1, _ := parser.ParseGo("a.go", []byte("package main\nfunc One() {}\n"))
	if err := s.UpsertFile(v1, "h1"); err != nil {
		t.Fatal(err)
	}
	v2, _ := parser.ParseGo("a.go", []byte("package main\nfunc Two() {}\n"))
	if err := s.UpsertFile(v2, "h2"); err != nil {
		t.Fatal(err)
	}

	syms, err := s.SymbolsInFile("a.go")
	if err != nil {
		t.Fatal(err)
	}
	if len(syms) != 1 || syms[0].Name != "Two" {
		t.Fatalf("expected only Two to remain after re-upsert, got %+v", syms)
	}

	hash, ok, err := s.FileHash("a.go")
	if err != nil || !ok || hash != "h2" {
		t.Fatalf("FileHash wrong: hash=%s ok=%v err=%v", hash, ok, err)
	}
}

func TestSymbolWithNoParamsOrReturnsIsNeverNil(t *testing.T) {
	// Regression test: "func main()" has zero params and zero returns, so
	// the parser leaves Symbol.Params/Returns as a nil Go slice. That
	// round-trips through SQLite as JSON "null" — Symbol() must normalize
	// it back to []Param{}, matching what API_CONTRACT.md documents and
	// what the frontend unconditionally .map()s/.length()s over. A nil
	// slice here used to crash the symbol detail page for every
	// zero-param function, including "main" itself.
	dbPath := filepath.Join(t.TempDir(), "graph.db")
	s, err := Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	fg, err := parser.ParseGo("main.go", []byte("package main\n\nfunc main() {\n\thelper()\n}\n"))
	if err != nil {
		t.Fatal(err)
	}
	if err := s.UpsertFile(fg, "hash1"); err != nil {
		t.Fatal(err)
	}

	sym, ok, err := s.Symbol("main.go:main")
	if err != nil || !ok {
		t.Fatalf("Symbol(main.go:main) failed: ok=%v err=%v", ok, err)
	}
	if sym.Params == nil {
		t.Error("expected Params to be a non-nil empty slice, got nil")
	}
	if sym.Returns == nil {
		t.Error("expected Returns to be a non-nil empty slice, got nil")
	}
}
