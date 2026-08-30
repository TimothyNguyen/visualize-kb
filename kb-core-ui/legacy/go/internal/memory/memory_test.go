package memory

import (
	"path/filepath"
	"testing"
	"time"
)

func newTestStore(t *testing.T) *Store {
	t.Helper()
	s, err := Open(filepath.Join(t.TempDir(), "memory.db"), NewHashingEmbedder(512))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

func TestEmbedderUnitLength(t *testing.T) {
	e := NewHashingEmbedder(256)
	v := e.Embed("the parser resolves call edges by receiver type")
	// Cosine of a vector with itself must be ~1 (unit length).
	if got := Cosine(v, v); got < 0.999 {
		t.Fatalf("expected unit vector self-cosine ~1, got %f", got)
	}
	if len(v) != 256 {
		t.Fatalf("expected dim 256, got %d", len(v))
	}
}

func TestEmbedderSimilarityRanking(t *testing.T) {
	e := NewHashingEmbedder(512)
	q := e.Embed("how are call graph edges resolved")
	related := e.Embed("call edges are resolved by matching the receiver type in the same package")
	unrelated := e.Embed("the frontend renders nodes with react flow and dagre layout")

	sRel := Cosine(q, related)
	sUnrel := Cosine(q, unrelated)
	if sRel <= sUnrel {
		t.Fatalf("expected related text to score higher: related=%f unrelated=%f", sRel, sUnrel)
	}
}

func TestAddAndSearch(t *testing.T) {
	s := newTestStore(t)
	now := time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)

	if _, err := s.Add(KindRule, "Edge resolution", "Call edges resolve by receiver type within the same package; never cross language families.", "test", now); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Add(KindOverview, "Frontend stack", "The web UI is React with @xyflow/react and dagre layout for the graph.", "test", now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Add(KindLesson, "Nil slices", "Zero-param Go functions store params as nil which serializes to JSON null; normalize to empty slice.", "test", now.Add(2*time.Second)); err != nil {
		t.Fatal(err)
	}

	n, err := s.Count()
	if err != nil || n != 3 {
		t.Fatalf("expected 3 entries, got %d (err %v)", n, err)
	}

	hits, err := s.Search("how do call edges get resolved between packages", "", 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(hits) == 0 {
		t.Fatal("expected at least one hit")
	}
	if hits[0].Title != "Edge resolution" {
		t.Fatalf("expected 'Edge resolution' to rank first, got %q (all: %v)", hits[0].Title, titles(hits))
	}
	// Scores must be descending.
	for i := 1; i < len(hits); i++ {
		if hits[i].Score > hits[i-1].Score {
			t.Fatalf("hits not sorted by score: %v", hits)
		}
	}
}

func TestSearchKindFilter(t *testing.T) {
	s := newTestStore(t)
	now := time.Now()
	s.Add(KindRule, "A rule about edges", "edges resolve by receiver", "t", now)
	s.Add(KindLesson, "A lesson about edges", "edges once dangled across files", "t", now)

	hits, err := s.Search("edges", KindLesson, 5)
	if err != nil {
		t.Fatal(err)
	}
	for _, h := range hits {
		if h.Kind != KindLesson {
			t.Fatalf("kind filter leaked a %s entry", h.Kind)
		}
	}
	if len(hits) != 1 {
		t.Fatalf("expected 1 lesson hit, got %d", len(hits))
	}
}

func TestGetListRemove(t *testing.T) {
	s := newTestStore(t)
	now := time.Now()
	e, err := s.Add(KindBusiness, "Pricing tiers", "Free tier caps at 3 repos; paid is unlimited.", "spec", now)
	if err != nil {
		t.Fatal(err)
	}

	got, ok, err := s.Get(e.ID)
	if err != nil || !ok {
		t.Fatalf("Get failed: ok=%v err=%v", ok, err)
	}
	if got.Title != "Pricing tiers" || got.Kind != KindBusiness {
		t.Fatalf("unexpected entry: %+v", got)
	}

	list, err := s.List("")
	if err != nil || len(list) != 1 {
		t.Fatalf("expected 1 entry, got %d (err %v)", len(list), err)
	}

	removed, err := s.Remove(e.ID)
	if err != nil || !removed {
		t.Fatalf("Remove failed: removed=%v err=%v", removed, err)
	}
	_, ok, _ = s.Get(e.ID)
	if ok {
		t.Fatal("entry should be gone after Remove")
	}
}

func TestStemmingBridgesMorphology(t *testing.T) {
	// The point of the v2 stemmer: a query and a doc that share only
	// morphological variants ("resolved packages" vs "resolve package")
	// must still match strongly at the word level, so the truly relevant
	// entry beats a tangential one that happens to share a raw token.
	e := NewHashingEmbedder(512)
	q := e.Embed("how are call edges resolved between packages")
	relevant := e.Embed("Call edge resolution\nCall edges resolve by receiver type within the same package.")
	tangential := e.Embed("What kb-core-ui is\nkb-core-ui parses a repo into a graph with symbols, call edges, and routes.")

	sRel := Cosine(q, relevant)
	sTan := Cosine(q, tangential)
	if sRel <= sTan {
		t.Fatalf("stemming should let the on-topic rule win: relevant=%.3f tangential=%.3f", sRel, sTan)
	}
	// And the win should be decisive, not marginal.
	if sRel < 2*sTan {
		t.Errorf("expected a decisive margin, got relevant=%.3f tangential=%.3f", sRel, sTan)
	}
}

func TestSearchDropsZeroScore(t *testing.T) {
	s := newTestStore(t)
	now := time.Now()
	s.Add(KindOverview, "Graph indexing", "tree-sitter parses files into symbols", "t", now)

	// A query sharing no vocabulary should return no hits (not a zero-score row).
	hits, err := s.Search("xyzzy quux frobnicate", "", 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(hits) != 0 {
		t.Fatalf("expected no hits for unrelated query, got %v", titles(hits))
	}
}

func titles(hits []Hit) []string {
	out := make([]string, len(hits))
	for i, h := range hits {
		out[i] = h.Title
	}
	return out
}
