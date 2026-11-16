// Package store persists a parsed repo's symbols, calls, and resolved
// edges in SQLite so `kb-core-ui serve` can restart instantly and
// incrementally re-parse only files that changed.
package store

import (
	"database/sql"
	"encoding/json"
	"fmt"

	_ "modernc.org/sqlite"

	"kb-core-ui/internal/graph"
)

const schema = `
CREATE TABLE IF NOT EXISTS files (
	path TEXT PRIMARY KEY,
	hash TEXT NOT NULL,
	language TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
	id TEXT PRIMARY KEY,
	file_path TEXT NOT NULL,
	name TEXT NOT NULL,
	kind TEXT NOT NULL,
	start_line INTEGER NOT NULL,
	end_line INTEGER NOT NULL,
	signature TEXT NOT NULL,
	params_json TEXT NOT NULL,
	returns_json TEXT NOT NULL,
	receiver TEXT NOT NULL,
	parent_id TEXT NOT NULL,
	language TEXT NOT NULL,
	doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_id);

CREATE TABLE IF NOT EXISTS unresolved_calls (
	file_path TEXT NOT NULL,
	from_id TEXT NOT NULL,
	target_name TEXT NOT NULL,
	kind TEXT NOT NULL,
	qualified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_calls_file ON unresolved_calls(file_path);

CREATE TABLE IF NOT EXISTS edges (
	source TEXT NOT NULL,
	target TEXT NOT NULL,
	kind TEXT NOT NULL,
	PRIMARY KEY (source, target, kind)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
`

// Store wraps a SQLite database holding one repo's code graph.
type Store struct {
	db *sql.DB
}

// Open creates/opens the SQLite database at path and ensures the schema
// exists.
func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("store: open %s: %w", path, err)
	}
	db.SetMaxOpenConns(1) // modernc sqlite: keep writes serialized, simplest correct option for a local dev tool
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, fmt.Errorf("store: apply schema: %w", err)
	}
	if err := migrate(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("store: migrate: %w", err)
	}
	return &Store{db: db}, nil
}

// migrate adds columns introduced after a database's initial CREATE TABLE
// ran — CREATE TABLE IF NOT EXISTS is a no-op against an existing file, so
// new columns need an explicit ALTER TABLE. This cache is fully rebuildable
// from source (delete .kb-core-ui/graph.db and re-run `kb-core-ui parse`), so
// there's nothing to backfill: existing rows just default to 0/false.
func migrate(db *sql.DB) error {
	rows, err := db.Query(`SELECT name FROM pragma_table_info('unresolved_calls')`)
	if err != nil {
		return err
	}
	hasQualified := false
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return err
		}
		if name == "qualified" {
			hasQualified = true
		}
	}
	if err := rows.Err(); err != nil {
		return err
	}
	rows.Close()
	if !hasQualified {
		if _, err := db.Exec(`ALTER TABLE unresolved_calls ADD COLUMN qualified INTEGER NOT NULL DEFAULT 0`); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) Close() error { return s.db.Close() }

// FileHash returns the last-indexed content hash for path, and whether the
// file has been indexed before at all.
func (s *Store) FileHash(path string) (string, bool, error) {
	var hash string
	err := s.db.QueryRow(`SELECT hash FROM files WHERE path = ?`, path).Scan(&hash)
	if err == sql.ErrNoRows {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return hash, true, nil
}

// KnownFiles returns every file path currently indexed, used to prune
// entries for files deleted since the last parse.
func (s *Store) KnownFiles() ([]string, error) {
	rows, err := s.db.Query(`SELECT path FROM files`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var paths []string
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return nil, err
		}
		paths = append(paths, p)
	}
	return paths, rows.Err()
}

// UpsertFile replaces one file's symbols and unresolved calls in a single
// transaction. Call RebuildEdges once after a batch of these to
// recompute resolved edges across the whole repo.
func (s *Store) UpsertFile(fg *graph.FileGraph, hash string) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	if err := deleteFile(tx, fg.FilePath); err != nil {
		return err
	}

	if _, err := tx.Exec(`INSERT INTO files(path, hash, language) VALUES (?, ?, ?)`,
		fg.FilePath, hash, fg.Language); err != nil {
		return err
	}

	for _, sym := range fg.Symbols {
		params, err := json.Marshal(sym.Params)
		if err != nil {
			return err
		}
		returns, err := json.Marshal(sym.Returns)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(`INSERT INTO symbols
			(id, file_path, name, kind, start_line, end_line, signature, params_json, returns_json, receiver, parent_id, language, doc)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			sym.ID, sym.FilePath, sym.Name, string(sym.Kind), sym.StartLine, sym.EndLine,
			sym.Signature, string(params), string(returns), sym.Receiver, sym.ParentID, sym.Language, sym.Doc,
		); err != nil {
			return err
		}
	}

	for _, c := range fg.UnresolvedCalls {
		if _, err := tx.Exec(`INSERT INTO unresolved_calls(file_path, from_id, target_name, kind, qualified) VALUES (?, ?, ?, ?, ?)`,
			fg.FilePath, c.FromID, c.TargetName, string(c.Kind), c.Qualified); err != nil {
			return err
		}
	}

	return tx.Commit()
}

// RemoveFile deletes a file (and its symbols/calls) that no longer exists
// on disk.
func (s *Store) RemoveFile(path string) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if err := deleteFile(tx, path); err != nil {
		return err
	}
	return tx.Commit()
}

func deleteFile(tx *sql.Tx, path string) error {
	if _, err := tx.Exec(`DELETE FROM files WHERE path = ?`, path); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM symbols WHERE file_path = ?`, path); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM unresolved_calls WHERE file_path = ?`, path); err != nil {
		return err
	}
	return nil
}

// RebuildEdges recomputes the resolved edge table from every symbol and
// unresolved call currently stored. Call once after a batch of UpsertFile
// calls, not per-file, since resolution needs the whole-repo symbol set.
func (s *Store) RebuildEdges() error {
	symbols, err := s.allSymbols()
	if err != nil {
		return err
	}
	calls, err := s.allUnresolvedCalls()
	if err != nil {
		return err
	}
	g := graph.BuildFlat(symbols, calls)

	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	// Persist any ParentIDs that BuildFlat corrected (a method whose type
	// lives in another file of the same package), so Members/SymbolsInFile
	// — which read parent_id straight from this table — agree with the
	// edges we're about to write.
	parentStmt, err := tx.Prepare(`UPDATE symbols SET parent_id = ? WHERE id = ?`)
	if err != nil {
		return err
	}
	defer parentStmt.Close()
	for _, orig := range symbols {
		corrected := g.Symbols[orig.ID].ParentID
		if corrected != orig.ParentID {
			if _, err := parentStmt.Exec(corrected, orig.ID); err != nil {
				return err
			}
		}
	}

	if _, err := tx.Exec(`DELETE FROM edges`); err != nil {
		return err
	}
	stmt, err := tx.Prepare(`INSERT OR IGNORE INTO edges(source, target, kind) VALUES (?, ?, ?)`)
	if err != nil {
		return err
	}
	defer stmt.Close()
	for _, e := range g.Edges {
		if _, err := stmt.Exec(e.Source, e.Target, string(e.Kind)); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) allSymbols() ([]graph.Symbol, error) {
	rows, err := s.db.Query(`SELECT id, file_path, name, kind, start_line, end_line, signature, params_json, returns_json, receiver, parent_id, language, doc FROM symbols`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []graph.Symbol
	for rows.Next() {
		sym, err := scanSymbol(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, sym)
	}
	return out, rows.Err()
}

func (s *Store) allUnresolvedCalls() ([]graph.UnresolvedCall, error) {
	rows, err := s.db.Query(`SELECT from_id, target_name, kind, qualified FROM unresolved_calls`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []graph.UnresolvedCall
	for rows.Next() {
		var c graph.UnresolvedCall
		var kind string
		if err := rows.Scan(&c.FromID, &c.TargetName, &kind, &c.Qualified); err != nil {
			return nil, err
		}
		c.Kind = graph.EdgeKind(kind)
		out = append(out, c)
	}
	return out, rows.Err()
}

type scanner interface {
	Scan(dest ...any) error
}

func scanSymbol(row scanner) (graph.Symbol, error) {
	var sym graph.Symbol
	var kind, paramsJSON, returnsJSON string
	if err := row.Scan(&sym.ID, &sym.FilePath, &sym.Name, &kind, &sym.StartLine, &sym.EndLine,
		&sym.Signature, &paramsJSON, &returnsJSON, &sym.Receiver, &sym.ParentID, &sym.Language, &sym.Doc); err != nil {
		return sym, err
	}
	sym.Kind = graph.SymbolKind(kind)
	if err := json.Unmarshal([]byte(paramsJSON), &sym.Params); err != nil {
		return sym, err
	}
	if err := json.Unmarshal([]byte(returnsJSON), &sym.Returns); err != nil {
		return sym, err
	}
	// A zero-param/zero-return symbol (e.g. "func main()", or a route with
	// no params of its own) stores its params/returns as JSON "null",
	// which json.Unmarshal leaves as a nil Go slice — that re-encodes to
	// the API response as `null` instead of `[]`. The frontend calls
	// .map()/.length on these unconditionally (per API_CONTRACT.md, an
	// empty array is the documented empty case, not null), so a nil slice
	// here crashes the page. Normalize to non-nil.
	if sym.Params == nil {
		sym.Params = []graph.Param{}
	}
	if sym.Returns == nil {
		sym.Returns = []graph.Param{}
	}
	return sym, nil
}
