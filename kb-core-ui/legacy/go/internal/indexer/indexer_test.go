package indexer

import (
	"os"
	"path/filepath"
	"testing"

	"kb-core-ui/internal/store"
)

func TestIndexScanReparseAndPrune(t *testing.T) {
	dir := t.TempDir()
	mustWrite(t, filepath.Join(dir, "a.go"), "package main\nfunc Add(a, b int) int { return helper(a, b) }\n")
	mustWrite(t, filepath.Join(dir, "b.go"), "package main\nfunc helper(a, b int) int { return a + b }\n")
	mustWrite(t, filepath.Join(dir, "node_modules", "skip.js"), "function skip() {}\n")

	dbPath := filepath.Join(t.TempDir(), "graph.db")
	s, err := store.Open(dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	res, err := Index(dir, s)
	if err != nil {
		t.Fatal(err)
	}
	if res.FilesChanged != 2 {
		t.Fatalf("expected 2 files indexed (node_modules skipped), got %+v", res)
	}

	stats, err := s.Stats()
	if err != nil {
		t.Fatal(err)
	}
	if stats.Symbols != 2 || stats.Edges != 1 {
		t.Fatalf("expected 2 symbols / 1 edge, got %+v", stats)
	}

	// Re-index with no changes: nothing should re-parse.
	res2, err := Index(dir, s)
	if err != nil {
		t.Fatal(err)
	}
	if res2.FilesChanged != 0 {
		t.Fatalf("expected 0 changed on unchanged re-index, got %+v", res2)
	}

	// Delete a file, re-index: it should be pruned from the store.
	if err := os.Remove(filepath.Join(dir, "b.go")); err != nil {
		t.Fatal(err)
	}
	res3, err := Index(dir, s)
	if err != nil {
		t.Fatal(err)
	}
	if res3.FilesRemoved != 1 {
		t.Fatalf("expected 1 file removed, got %+v", res3)
	}
	syms, err := s.SymbolsInFile("b.go")
	if err != nil {
		t.Fatal(err)
	}
	if len(syms) != 0 {
		t.Fatalf("expected b.go symbols gone after prune, got %+v", syms)
	}
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
