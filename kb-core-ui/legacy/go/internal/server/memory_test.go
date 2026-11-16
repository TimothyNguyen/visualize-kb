package server

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"kb-core-ui/internal/memory"
	"kb-core-ui/internal/store"
)

func memServer(t *testing.T) *httptest.Server {
	t.Helper()
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
	ts := httptest.NewServer(New(s, t.TempDir(), "", nil, mem))
	t.Cleanup(ts.Close)
	return ts
}

func TestMemoryEndpoints(t *testing.T) {
	ts := memServer(t)

	// POST /api/memory
	body := `{"kind":"rule","title":"Edge resolution","text":"Call edges resolve by receiver type within the same package."}`
	resp, err := http.Post(ts.URL+"/api/memory", "application/json", bytes.NewReader([]byte(body)))
	if err != nil {
		t.Fatal(err)
	}
	var entry memory.Entry
	json.NewDecoder(resp.Body).Decode(&entry)
	resp.Body.Close()
	if entry.ID == "" || entry.Kind != memory.KindRule {
		t.Fatalf("unexpected created entry: %+v", entry)
	}

	// GET /api/memory
	var list []memory.Entry
	getJSON(t, ts.URL+"/api/memory", &list)
	if len(list) != 1 {
		t.Fatalf("expected 1 entry, got %d", len(list))
	}

	// GET /api/memory/search
	var hits []memory.Hit
	getJSON(t, ts.URL+"/api/memory/search?q=how+are+call+edges+resolved+in+a+package", &hits)
	if len(hits) == 0 || hits[0].Title != "Edge resolution" {
		t.Fatalf("search did not recall the rule: %+v", hits)
	}

	// Invalid kind on add -> 400
	bad, err := http.Post(ts.URL+"/api/memory", "application/json", bytes.NewReader([]byte(`{"kind":"nope","title":"x","text":"y"}`)))
	if err != nil {
		t.Fatal(err)
	}
	bad.Body.Close()
	if bad.StatusCode != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid kind, got %d", bad.StatusCode)
	}

	// DELETE /api/memory/:id
	req, _ := http.NewRequest(http.MethodDelete, ts.URL+"/api/memory/"+entry.ID, nil)
	del, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	del.Body.Close()
	if del.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 on delete, got %d", del.StatusCode)
	}

	var after []memory.Entry
	getJSON(t, ts.URL+"/api/memory", &after)
	if len(after) != 0 {
		t.Fatalf("expected 0 entries after delete, got %d", len(after))
	}
}
