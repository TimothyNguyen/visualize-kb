package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"kb-core-ui/internal/graph"
	"kb-core-ui/internal/indexer"
	"kb-core-ui/internal/store"
)

func setup(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	root := t.TempDir()
	// Nested under pkg/ so symbol ids (filePath + ":" + name) contain a "/"
	// — needed to exercise the %2F-in-id routing path, see encodedID below.
	mustWrite(t, filepath.Join(root, "pkg", "a.go"), "package main\n\n// Add sums two ints.\nfunc Add(a int, b int) int {\n\treturn helper(a, b)\n}\n")
	mustWrite(t, filepath.Join(root, "pkg", "b.go"), "package main\n\nfunc helper(a int, b int) int {\n\treturn a + b\n}\n")

	dbPath := filepath.Join(t.TempDir(), "graph.db")
	s, err := store.Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })

	if _, err := indexer.Index(root, s); err != nil {
		t.Fatal(err)
	}

	srv := New(s, root, "", nil, nil)
	ts := httptest.NewServer(srv)
	t.Cleanup(ts.Close)
	return ts, root
}

func mustWrite(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func getJSON(t *testing.T, url string, v any) *http.Response {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatal(err)
	}
	if v != nil {
		defer resp.Body.Close()
		if err := json.NewDecoder(resp.Body).Decode(v); err != nil {
			t.Fatalf("decode %s: %v", url, err)
		}
	}
	return resp
}

func TestEndpoints(t *testing.T) {
	ts, _ := setup(t)

	var tree graph.TreeNode
	getJSON(t, ts.URL+"/api/tree", &tree)
	if len(tree.Children) != 1 || tree.Children[0].Name != "pkg" || len(tree.Children[0].Children) != 2 {
		t.Fatalf("expected 1 top-level dir \"pkg\" with 2 files, got %+v", tree)
	}

	var stats map[string]any
	getJSON(t, ts.URL+"/api/stats", &stats)
	if stats["files"].(float64) != 2 || stats["symbols"].(float64) != 2 || stats["edges"].(float64) != 1 {
		t.Fatalf("unexpected stats: %+v", stats)
	}

	var syms []graph.SymbolRef
	getJSON(t, ts.URL+"/api/files/pkg/a.go/symbols", &syms)
	if len(syms) != 1 || syms[0].Name != "Add" {
		t.Fatalf("unexpected file symbols: %+v", syms)
	}
	addID := syms[0].ID

	// addID contains "/" (it embeds the file path, e.g. "a.go:Add") — the
	// real frontend percent-encodes ids with encodeURIComponent before
	// building the URL, so the test must too, or it'd miss a routing bug
	// that only bites once %2F shows up on the wire.
	encodedID := url.PathEscape(addID)
	if !strings.Contains(encodedID, "%") {
		t.Fatalf("test id %q has no path separator to encode; strengthen the fixture", addID)
	}

	var sym graph.Symbol
	getJSON(t, ts.URL+"/api/symbols/"+encodedID, &sym)
	if sym.Name != "Add" || sym.Doc == "" || len(sym.Params) != 2 {
		t.Fatalf("unexpected symbol detail: %+v", sym)
	}

	var calls []map[string]any
	getJSON(t, ts.URL+"/api/symbols/"+encodedID+"/calls", &calls)
	if len(calls) != 1 {
		t.Fatalf("expected 1 outgoing call, got %+v", calls)
	}
	if _, ok := calls[0]["edge"]; !ok {
		t.Fatalf(`expected lowercase "edge" field per API_CONTRACT.md, got %+v`, calls[0])
	}
	if _, ok := calls[0]["symbol"]; !ok {
		t.Fatalf(`expected lowercase "symbol" field per API_CONTRACT.md, got %+v`, calls[0])
	}

	var noCallers []any
	getJSON(t, ts.URL+"/api/symbols/"+encodedID+"/callers", &noCallers)
	if noCallers == nil {
		t.Fatal("expected /callers with no results to decode as [], got null")
	}

	var g map[string]any
	getJSON(t, ts.URL+"/api/graph", &g)
	if len(g["nodes"].([]any)) != 2 || len(g["edges"].([]any)) != 1 {
		t.Fatalf("unexpected full graph: %+v", g)
	}

	var sub map[string]any
	getJSON(t, ts.URL+"/api/graph/subgraph?symbol="+url.QueryEscape(addID)+"&depth=2", &sub)
	if sub["center"] != addID {
		t.Fatalf("unexpected subgraph center: %+v", sub)
	}

	var results []graph.SymbolRef
	getJSON(t, ts.URL+"/api/search?q=Add", &results)
	if len(results) != 1 || results[0].ID != addID {
		t.Fatalf("unexpected search results: %+v", results)
	}

	var src map[string]any
	getJSON(t, ts.URL+"/api/source?file=pkg/a.go&start=1&end=3", &src)
	lines := src["lines"].([]any)
	if len(lines) != 3 {
		t.Fatalf("expected 3 source lines, got %+v", src)
	}

	resp := getJSON(t, ts.URL+"/api/symbols/does-not-exist", nil)
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown symbol, got %d", resp.StatusCode)
	}
}
