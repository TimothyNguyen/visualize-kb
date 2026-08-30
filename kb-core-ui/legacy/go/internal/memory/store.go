// Package memory is kb-core-ui's vector memory: a semantic store of non-code
// knowledge — codebase rules, lessons learned, business-logic notes, "what
// this software does" — kept separate from the code graph. Entries are
// embedded into vectors and retrieved by cosine similarity, so an AI agent
// or bot can pull the few relevant rules/lessons for a task instead of
// being handed everything. The code graph answers "where does this code
// live"; this answers "what do we know that isn't in the code".
package memory

import (
	"database/sql"
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// Kind classifies a memory entry.
type Kind string

const (
	KindRule     Kind = "rule"      // a primary codebase rule / invariant
	KindLesson   Kind = "lesson"    // a lesson learned (e.g. from a bug)
	KindBusiness Kind = "business"  // a business-logic / data-dependency note
	KindOverview Kind = "overview"  // what the software / a subsystem does
	KindRef      Kind = "reference" // pointer to an external resource
)

// Entry is one stored memory (JSON tags mirror the REST contract).
type Entry struct {
	ID        string    `json:"id"`
	Kind      Kind      `json:"kind"`
	Title     string    `json:"title"`
	Text      string    `json:"text"`
	Source    string    `json:"source,omitempty"` // where it came from (bot, file, url, person)
	CreatedAt time.Time `json:"createdAt"`
}

// Hit is an Entry paired with its similarity score for a search result.
type Hit struct {
	Entry `json:"entry"`
	Score float64 `json:"score"`
}

// Store persists memory entries and their embeddings in SQLite.
type Store struct {
	db       *sql.DB
	embedder Embedder
}

const memSchema = `
CREATE TABLE IF NOT EXISTS memories (
	id          TEXT PRIMARY KEY,
	kind        TEXT NOT NULL,
	title       TEXT NOT NULL,
	text        TEXT NOT NULL,
	source      TEXT NOT NULL,
	created_at  TEXT NOT NULL,
	embedder    TEXT NOT NULL,
	dim         INTEGER NOT NULL,
	embedding   BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
`

// Open opens/creates the memory DB at path with the given embedder.
func Open(path string, embedder Embedder) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("memory: open %s: %w", path, err)
	}
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(memSchema); err != nil {
		db.Close()
		return nil, fmt.Errorf("memory: schema: %w", err)
	}
	return &Store{db: db, embedder: embedder}, nil
}

func (s *Store) Close() error { return s.db.Close() }

// Add embeds and stores a new entry, returning it with its generated id and
// timestamp. now is injectable for tests.
func (s *Store) Add(kind Kind, title, text, source string, now time.Time) (Entry, error) {
	// Embed title+text together — the title carries strong signal.
	vec := s.embedder.Embed(title + "\n" + text)
	id := makeID(kind, title, now)
	e := Entry{ID: id, Kind: kind, Title: title, Text: text, Source: source, CreatedAt: now}
	_, err := s.db.Exec(
		`INSERT INTO memories(id, kind, title, text, source, created_at, embedder, dim, embedding)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		e.ID, string(e.Kind), e.Title, e.Text, e.Source, e.CreatedAt.Format(time.RFC3339Nano),
		s.embedder.Name(), s.embedder.Dim(), encodeVec(vec),
	)
	if err != nil {
		return Entry{}, err
	}
	return e, nil
}

// Search returns the top-k entries most similar to query, filtered to kind
// if non-empty. It's a brute-force cosine scan — fine for the thousands of
// entries this kind of memory holds; swap in an ANN index if it grows huge.
func (s *Store) Search(query string, kind Kind, k int) ([]Hit, error) {
	if k <= 0 {
		k = 5
	}
	qvec := s.embedder.Embed(query)

	q := `SELECT id, kind, title, text, source, created_at, embedder, dim, embedding FROM memories`
	var args []any
	if kind != "" {
		q += ` WHERE kind = ?`
		args = append(args, string(kind))
	}
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var hits []Hit
	for rows.Next() {
		e, embName, blob, err := scanEntry(rows)
		if err != nil {
			return nil, err
		}
		// Only compare against vectors from the same embedder — mixing
		// models would produce meaningless scores.
		if embName != s.embedder.Name() {
			continue
		}
		score := Cosine(qvec, decodeVec(blob))
		hits = append(hits, Hit{Entry: e, Score: score})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	// Drop weak matches below the noise floor: the hashing embedder gives
	// even unrelated text a small nonzero similarity from feature-hash
	// collisions, and returning a misleading "relevant rule" when nothing
	// really matches is worse than returning nothing.
	filtered := hits[:0]
	for _, h := range hits {
		if h.Score >= MinScore {
			filtered = append(filtered, h)
		}
	}
	if len(filtered) > k {
		filtered = filtered[:k]
	}
	return filtered, nil
}

// MinScore is the cosine-similarity floor below which a search result is
// treated as noise (hash collisions) rather than a real match. Calibrated
// for the lexical HashingEmbedder, whose genuine weak matches land around
// 0.10 while feature-hash collision noise sits under ~0.05. A neural
// embedder would warrant a different, higher floor.
const MinScore = 0.07

// List returns all entries (newest first), optionally filtered by kind.
func (s *Store) List(kind Kind) ([]Entry, error) {
	q := `SELECT id, kind, title, text, source, created_at, embedder, dim, embedding FROM memories`
	var args []any
	if kind != "" {
		q += ` WHERE kind = ?`
		args = append(args, string(kind))
	}
	q += ` ORDER BY created_at DESC`
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Entry
	for rows.Next() {
		e, _, _, err := scanEntry(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// Get returns one entry by id, or ok=false.
func (s *Store) Get(id string) (Entry, bool, error) {
	row := s.db.QueryRow(`SELECT id, kind, title, text, source, created_at, embedder, dim, embedding FROM memories WHERE id = ?`, id)
	e, _, _, err := scanEntry(row)
	if err == sql.ErrNoRows {
		return Entry{}, false, nil
	}
	if err != nil {
		return Entry{}, false, err
	}
	return e, true, nil
}

// Remove deletes an entry; returns whether a row was deleted.
func (s *Store) Remove(id string) (bool, error) {
	res, err := s.db.Exec(`DELETE FROM memories WHERE id = ?`, id)
	if err != nil {
		return false, err
	}
	n, _ := res.RowsAffected()
	return n > 0, nil
}

// Count returns the number of stored entries.
func (s *Store) Count() (int, error) {
	var n int
	err := s.db.QueryRow(`SELECT COUNT(*) FROM memories`).Scan(&n)
	return n, err
}

type scanner interface {
	Scan(dest ...any) error
}

func scanEntry(row scanner) (Entry, string, []byte, error) {
	var e Entry
	var kind, createdAt, embName string
	var dim int
	var blob []byte
	if err := row.Scan(&e.ID, &kind, &e.Title, &e.Text, &e.Source, &createdAt, &embName, &dim, &blob); err != nil {
		return Entry{}, "", nil, err
	}
	e.Kind = Kind(kind)
	t, err := time.Parse(time.RFC3339Nano, createdAt)
	if err == nil {
		e.CreatedAt = t
	}
	return e, embName, blob, nil
}

func makeID(kind Kind, title string, now time.Time) string {
	slug := strings.Map(func(r rune) rune {
		switch {
		case r >= 'a' && r <= 'z', r >= '0' && r <= '9':
			return r
		case r >= 'A' && r <= 'Z':
			return r + 32
		case r == ' ' || r == '-' || r == '_':
			return '-'
		default:
			return -1
		}
	}, title)
	if len(slug) > 40 {
		slug = slug[:40]
	}
	slug = strings.Trim(slug, "-")
	if slug == "" {
		slug = "mem"
	}
	return fmt.Sprintf("%s-%s-%d", kind, slug, now.UnixNano())
}

// encodeVec/decodeVec serialize a float32 vector as little-endian bytes.
func encodeVec(v []float32) []byte {
	b := make([]byte, 4*len(v))
	for i, f := range v {
		binary.LittleEndian.PutUint32(b[i*4:], math.Float32bits(f))
	}
	return b
}

func decodeVec(b []byte) []float32 {
	v := make([]float32, len(b)/4)
	for i := range v {
		v[i] = math.Float32frombits(binary.LittleEndian.Uint32(b[i*4:]))
	}
	return v
}
