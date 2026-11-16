package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	"github.com/spf13/cobra"

	"kb-core-ui/internal/indexer"
	"kb-core-ui/internal/store"
)

// resolveRepoPath turns the optional positional path arg into an absolute
// repo root, defaulting to the current directory.
func resolveRepoPath(args []string) (string, error) {
	path := "."
	if len(args) > 0 {
		path = args[0]
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	info, err := os.Stat(abs)
	if err != nil {
		return "", fmt.Errorf("repo path %s: %w", abs, err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("repo path %s is not a directory", abs)
	}
	return abs, nil
}

// openStoreAndIndex opens (creating if needed) the repo's graph DB and runs
// an incremental index pass, printing a one-line progress summary.
func openStoreAndIndex(cmd *cobra.Command, repoRoot, dbPath string) (*store.Store, error) {
	if dbPath == "" {
		dbPath = indexer.DefaultDBPath(repoRoot)
	}
	if err := indexer.EnsureDBDir(repoRoot); err != nil {
		return nil, err
	}
	s, err := store.Open(dbPath)
	if err != nil {
		return nil, err
	}

	cmd.Printf("Indexing %s...\n", repoRoot)
	res, err := indexer.Index(repoRoot, s)
	if err != nil {
		s.Close()
		return nil, fmt.Errorf("index: %w", err)
	}
	stats, err := s.Stats()
	if err != nil {
		s.Close()
		return nil, err
	}
	cmd.Printf("Indexed %d files (%d changed, %d removed) -> %d symbols, %d edges. DB: %s\n",
		res.FilesScanned, res.FilesChanged, res.FilesRemoved, stats.Symbols, stats.Edges, dbPath)

	return s, nil
}

// locateWebDir looks for the built frontend (web/dist) in a few sensible
// places: next to the kb-core-ui executable, or in this source tree during
// local development. Returns "" if none is found.
func locateWebDir(explicit string) string {
	if explicit != "" {
		return explicit
	}
	candidates := []string{}
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "web", "dist"))
	}
	if wd, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(wd, "web", "dist"))
	}
	if _, thisFile, _, ok := runtime.Caller(0); ok {
		// this file lives at cmd/kb-core-ui/common.go; web/dist is a sibling of cmd/
		candidates = append(candidates, filepath.Join(filepath.Dir(filepath.Dir(filepath.Dir(thisFile))), "web", "dist"))
	}
	for _, c := range candidates {
		if info, err := os.Stat(filepath.Join(c, "index.html")); err == nil && !info.IsDir() {
			return c
		}
	}
	return ""
}
