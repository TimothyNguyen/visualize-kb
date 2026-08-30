// Package indexer walks a repo directory, parses every file a parser
// supports, and writes the result into a store.Store — incrementally,
// skipping files whose content hash hasn't changed since the last run.
package indexer

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"

	"kb-core-ui/internal/parser"
	"kb-core-ui/internal/store"
)

// skipDirs are directories never worth descending into: VCS metadata,
// dependency trees, and build output. None of these hold hand-written
// source a developer would want in the graph.
var skipDirs = map[string]bool{
	".git": true, "node_modules": true, "vendor": true, "dist": true, "build": true,
	".next": true, "__pycache__": true, "venv": true, ".venv": true, "target": true,
	".kb-core-ui": true,
}

// Result summarizes one indexing run.
type Result struct {
	FilesScanned int
	FilesChanged int
	FilesRemoved int
}

// Index walks root, parses every changed/new supported file into s, prunes
// files that no longer exist, and rebuilds the resolved edge table once at
// the end (edge resolution needs the whole repo's symbols, so it can't be
// done per-file).
func Index(root string, s *store.Store) (Result, error) {
	var res Result
	seen := make(map[string]bool)

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if skipDirs[d.Name()] && path != root {
				return filepath.SkipDir
			}
			return nil
		}
		if _, ok := parser.LanguageFor(path); !ok {
			return nil
		}

		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		seen[rel] = true
		res.FilesScanned++

		src, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("indexer: read %s: %w", rel, err)
		}
		hash := contentHash(src)

		prevHash, known, err := s.FileHash(rel)
		if err != nil {
			return err
		}
		if known && prevHash == hash {
			return nil
		}

		fg, err := parser.ParseFile(rel, src)
		if err != nil {
			return fmt.Errorf("indexer: parse %s: %w", rel, err)
		}
		if err := s.UpsertFile(fg, hash); err != nil {
			return fmt.Errorf("indexer: store %s: %w", rel, err)
		}
		res.FilesChanged++
		return nil
	})
	if err != nil {
		return res, err
	}

	known, err := s.KnownFiles()
	if err != nil {
		return res, err
	}
	for _, path := range known {
		if !seen[path] {
			if err := s.RemoveFile(path); err != nil {
				return res, err
			}
			res.FilesRemoved++
		}
	}

	if res.FilesChanged > 0 || res.FilesRemoved > 0 {
		if err := s.RebuildEdges(); err != nil {
			return res, fmt.Errorf("indexer: rebuild edges: %w", err)
		}
	}

	return res, nil
}

func contentHash(src []byte) string {
	sum := sha256.Sum256(src)
	return hex.EncodeToString(sum[:])
}

// DefaultDBPath returns the default SQLite path for a repo root:
// <root>/.kb-core-ui/graph.db.
func DefaultDBPath(root string) string {
	return filepath.Join(root, ".kb-core-ui", "graph.db")
}

// EnsureDBDir makes sure the directory holding DefaultDBPath exists.
func EnsureDBDir(root string) error {
	return os.MkdirAll(filepath.Join(root, ".kb-core-ui"), 0o755)
}
