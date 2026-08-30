package mcp

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/mark3labs/mcp-go/client"
	gomcp "github.com/mark3labs/mcp-go/mcp"

	"kb-core-ui/internal/graph"
	"kb-core-ui/internal/indexer"
	"kb-core-ui/internal/memory"
	"kb-core-ui/internal/store"
)

func setup(t *testing.T) (*client.Client, string) {
	t.Helper()
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "a.go"),
		[]byte("package main\n\n// Add sums two ints.\nfunc Add(a int, b int) int {\n\treturn helper(a, b)\n}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "b.go"),
		[]byte("package main\n\nfunc helper(a int, b int) int {\n\treturn a + b\n}\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	s, err := store.Open(filepath.Join(t.TempDir(), "graph.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	if _, err := indexer.Index(root, s); err != nil {
		t.Fatal(err)
	}

	srv := New(s, root, nil)
	c, err := client.NewInProcessClient(srv)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := c.Initialize(context.Background(), gomcp.InitializeRequest{}); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Close() })
	return c, root
}

// setupWithMemory is like setup but also wires a vector memory store, so the
// memory_* MCP tools are available.
func setupWithMemory(t *testing.T) *client.Client {
	t.Helper()
	root := t.TempDir()
	s, err := store.Open(filepath.Join(t.TempDir(), "graph.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })

	mem, err := memory.Open(filepath.Join(t.TempDir(), "memory.db"), memory.NewHashingEmbedder(512))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { mem.Close() })

	srv := New(s, root, mem)
	c, err := client.NewInProcessClient(srv)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := c.Initialize(context.Background(), gomcp.InitializeRequest{}); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Close() })
	return c
}

func TestMCPMemoryTools(t *testing.T) {
	c := setupWithMemory(t)

	// memory_add persists a rule.
	added := callTool(t, c, "memory_add", map[string]any{
		"kind":  "rule",
		"title": "Edge resolution",
		"text":  "Call edges resolve by receiver type within the same package; never across language families.",
	})
	if !contains(added, "Edge resolution") {
		t.Fatalf("memory_add did not echo the entry: %s", added)
	}

	// memory_search finds it back.
	var hits []memory.Hit
	if err := json.Unmarshal([]byte(callTool(t, c, "memory_search", map[string]any{
		"query": "how do call edges get resolved between packages",
	})), &hits); err != nil {
		t.Fatal(err)
	}
	if len(hits) == 0 || hits[0].Title != "Edge resolution" {
		t.Fatalf("memory_search did not recall the rule: %+v", hits)
	}

	// Invalid kind is rejected.
	res, err := c.CallTool(context.Background(), gomcp.CallToolRequest{
		Params: gomcp.CallToolParams{Name: "memory_add", Arguments: map[string]any{
			"kind": "bogus", "title": "x", "text": "y",
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !res.IsError {
		t.Fatal("expected an error result for an invalid memory kind")
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

func callTool(t *testing.T, c *client.Client, name string, args map[string]any) string {
	t.Helper()
	res, err := c.CallTool(context.Background(), gomcp.CallToolRequest{
		Params: gomcp.CallToolParams{Name: name, Arguments: args},
	})
	if err != nil {
		t.Fatalf("%s: %v", name, err)
	}
	if res.IsError {
		t.Fatalf("%s returned tool error: %s", name, gomcp.GetTextFromContent(res.Content[0]))
	}
	return gomcp.GetTextFromContent(res.Content[0])
}

func TestMCPToolsEndToEnd(t *testing.T) {
	c, _ := setup(t)

	var searchResults []graph.SymbolRef
	if err := json.Unmarshal([]byte(callTool(t, c, "search_symbol", map[string]any{"query": "Add"})), &searchResults); err != nil {
		t.Fatal(err)
	}
	if len(searchResults) != 1 || searchResults[0].Name != "Add" {
		t.Fatalf("unexpected search_symbol result: %+v", searchResults)
	}
	addID := searchResults[0].ID

	var sym graph.Symbol
	if err := json.Unmarshal([]byte(callTool(t, c, "get_symbol", map[string]any{"id": addID})), &sym); err != nil {
		t.Fatal(err)
	}
	if sym.Doc == "" || len(sym.Params) != 2 {
		t.Fatalf("unexpected get_symbol result: %+v", sym)
	}

	var fileSyms []graph.SymbolRef
	if err := json.Unmarshal([]byte(callTool(t, c, "get_file_symbols", map[string]any{"path": "a.go"})), &fileSyms); err != nil {
		t.Fatal(err)
	}
	if len(fileSyms) != 1 {
		t.Fatalf("unexpected get_file_symbols result: %+v", fileSyms)
	}

	var callees []map[string]any
	if err := json.Unmarshal([]byte(callTool(t, c, "get_callees", map[string]any{"id": addID})), &callees); err != nil {
		t.Fatal(err)
	}
	if len(callees) != 1 {
		t.Fatalf("expected 1 callee, got %+v", callees)
	}
	symField, ok := callees[0]["symbol"].(map[string]any)
	if !ok {
		t.Fatalf("get_callees result missing lowercase \"symbol\" field (json tags?): %+v", callees[0])
	}
	helperID := symField["id"].(string)

	var callers []map[string]any
	if err := json.Unmarshal([]byte(callTool(t, c, "get_callers", map[string]any{"id": helperID})), &callers); err != nil {
		t.Fatal(err)
	}
	if len(callers) != 1 {
		t.Fatalf("expected 1 caller of helper, got %+v", callers)
	}

	slice := callTool(t, c, "get_file_slice", map[string]any{"file": "a.go", "start": float64(4), "end": float64(6)})
	if slice == "" {
		t.Fatal("expected non-empty file slice")
	}

	tree := callTool(t, c, "get_tree", map[string]any{})
	if tree == "" {
		t.Fatal("expected non-empty tree")
	}

	stats := callTool(t, c, "get_stats", map[string]any{})
	if stats == "" {
		t.Fatal("expected non-empty stats")
	}
}
