package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"kb-core-ui/internal/bots"
	"kb-core-ui/internal/store"
)

func botTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	root := t.TempDir()

	// A fake kb-core-ui binary the runner will invoke; it just echoes and exits 0.
	fake := filepath.Join(root, "fake-kb-core-ui")
	if err := os.WriteFile(fake, []byte("#!/bin/sh\necho ran: \"$@\"\n"), 0o755); err != nil {
		t.Fatal(err)
	}

	s, err := store.Open(filepath.Join(t.TempDir(), "graph.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })

	runner := bots.NewRunner(fake, root)
	srv := New(s, root, "", runner, nil)
	ts := httptest.NewServer(srv)
	t.Cleanup(ts.Close)
	return ts
}

func TestBotsEndpoints(t *testing.T) {
	ts := botTestServer(t)

	// GET /api/bots — roster.
	var defs []bots.Def
	getJSON(t, ts.URL+"/api/bots", &defs)
	if len(defs) < 2 {
		t.Fatalf("expected the bot roster, got %d", len(defs))
	}
	var haveGraphSync bool
	for _, d := range defs {
		if d.Name == "graph-sync" {
			haveGraphSync = true
		}
	}
	if !haveGraphSync {
		t.Fatal("expected graph-sync in the roster")
	}

	// POST /api/bots/graph-sync/run — start a run.
	resp, err := http.Post(ts.URL+"/api/bots/graph-sync/run", "application/json", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	var run bots.Run
	json.NewDecoder(resp.Body).Decode(&run)
	resp.Body.Close()
	if run.ID == "" || run.Bot != "graph-sync" {
		t.Fatalf("unexpected run: %+v", run)
	}

	// Poll GET /api/bots/runs/:id until it finishes.
	var final bots.Run
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		getJSON(t, ts.URL+"/api/bots/runs/"+run.ID, &final)
		if final.Status != "running" {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if final.Status != "succeeded" {
		t.Fatalf("expected succeeded, got %q (output %q)", final.Status, final.Output)
	}
	if final.Output == "" {
		t.Fatal("expected captured output")
	}

	// GET /api/bots/runs — the run shows in history.
	var summaries []bots.RunSummary
	getJSON(t, ts.URL+"/api/bots/runs", &summaries)
	if len(summaries) != 1 || summaries[0].ID != run.ID {
		t.Fatalf("expected 1 run in history, got %+v", summaries)
	}

	// Missing required arg -> 400.
	resp2, err := http.Post(ts.URL+"/api/bots/pr-review/run", "application/json", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	resp2.Body.Close()
	if resp2.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing pr_number, got %d", resp2.StatusCode)
	}

	// Unknown bot -> 404.
	resp3, err := http.Post(ts.URL+"/api/bots/nope/run", "application/json", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	resp3.Body.Close()
	if resp3.StatusCode != http.StatusNotFound {
		t.Fatalf("expected 404 for unknown bot, got %d", resp3.StatusCode)
	}
}

func TestBotsDisabledWhenNoRunner(t *testing.T) {
	s, err := store.Open(filepath.Join(t.TempDir(), "graph.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	ts := httptest.NewServer(New(s, t.TempDir(), "", nil, nil))
	t.Cleanup(ts.Close)

	// With no runner, /api/bots isn't registered — the SPA/notfound handler
	// responds instead, so it must not be a 200 JSON bot roster.
	resp, err := http.Get(ts.URL + "/api/bots")
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode == http.StatusOK {
		t.Fatalf("expected /api/bots to be unavailable without a runner, got 200")
	}
}
