package main

import (
	"fmt"

	"github.com/spf13/cobra"

	"kb-core-ui/internal/indexer"
	"kb-core-ui/internal/store"
)

// The graph-sync bot is Go-native rather than a Python script: it does pure
// graph work (re-index + integrity check) with no AI/claude involvement, so
// it has no auth dependency and runs anywhere the binary does. The `bots/`
// Python scripts are for the AI-driven bots; this lives with the CLI.
func newBotGraphSyncCmd() *cobra.Command {
	var repoPath, dbPath string
	var checkOnly, failOnStale bool
	cmd := &cobra.Command{
		Use:   "graph-sync",
		Short: "Re-index the repo graph and check its integrity (no AI, no auth needed)",
		Long: `Keeps the code graph fresh and verifies it's sound — the "update graph,
check graph" bot. Re-indexes changed files, then reports resolution
quality and integrity (dangling edges, unresolved-call hotspots). A stale
or broken graph silently makes every AI bot wrong, so this is the
foundation the others depend on.

Runs without AI or authentication.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			resolvedDB := dbPath
			if resolvedDB == "" {
				resolvedDB = indexer.DefaultDBPath(repoRoot)
			}

			var res indexer.Result
			if !checkOnly {
				if err := indexer.EnsureDBDir(repoRoot); err != nil {
					return err
				}
				s, err := store.Open(resolvedDB)
				if err != nil {
					return err
				}
				cmd.Printf("Indexing %s...\n", repoRoot)
				res, err = indexer.Index(repoRoot, s)
				s.Close()
				if err != nil {
					return fmt.Errorf("index: %w", err)
				}
				cmd.Printf("Indexed %d files (%d changed, %d removed).\n",
					res.FilesScanned, res.FilesChanged, res.FilesRemoved)
			}

			s, err := store.Open(resolvedDB)
			if err != nil {
				return err
			}
			defer s.Close()

			h, err := s.Health()
			if err != nil {
				return fmt.Errorf("graph health check: %w", err)
			}
			printHealth(cmd, h)

			if h.DanglingEdges > 0 {
				return fmt.Errorf("graph integrity check FAILED: %d dangling edge(s) reference missing symbols — the DB is corrupt; delete %s and re-run", h.DanglingEdges, resolvedDB)
			}
			// --fail-on-stale lets CI enforce "the committed graph matches
			// the committed code": if re-indexing had to change anything,
			// the graph someone committed was stale.
			if failOnStale && (res.FilesChanged > 0 || res.FilesRemoved > 0) {
				return fmt.Errorf("graph was stale: re-indexing changed %d file(s) and removed %d — commit a fresh graph or run graph-sync before pushing", res.FilesChanged, res.FilesRemoved)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "path to the local repo checkout")
	cmd.Flags().StringVar(&dbPath, "db", "", "path to the SQLite graph DB (default: <repo>/.kb-core-ui/graph.db)")
	cmd.Flags().BoolVar(&checkOnly, "check-only", false, "only check the existing graph, don't re-index")
	cmd.Flags().BoolVar(&failOnStale, "fail-on-stale", false, "exit non-zero if re-indexing found changes (CI: enforce a fresh graph)")
	return cmd
}

func printHealth(cmd *cobra.Command, h store.Health) {
	cmd.Println("\nGraph health:")
	cmd.Printf("  files:                 %d\n", h.Files)
	cmd.Printf("  symbols:               %d\n", h.Symbols)
	cmd.Printf("  edges:                 %d\n", h.Edges)

	// Integrity is the pass/fail signal — dangling edges mean the graph is
	// internally inconsistent (a real defect). This is what the bot gates on.
	if h.DanglingEdges == 0 {
		cmd.Println("  integrity:             OK (no dangling edges)")
	} else {
		cmd.Printf("  integrity:             FAIL (%d dangling edges)\n", h.DanglingEdges)
	}

	// Resolution rate is informational, NOT a health score: a call to a
	// stdlib/third-party function (fmt.Println, useState, ...) correctly
	// stays "unresolved" because that code isn't in this repo. A low rate
	// is normal and expected; it only measures how self-contained the code
	// is, not whether the graph is good.
	cmd.Printf("  internal calls linked: %d of %d call sites (%.0f%% — rest are stdlib/third-party, expected)\n",
		h.ResolvedCalls, h.ResolvedCalls+h.UnresolvedCalls, h.ResolutionRate*100)

	if len(h.TopUnresolvedFiles) > 0 {
		cmd.Println("  most external calls (informational — high counts are normal for glue/IO-heavy files):")
		for _, fc := range h.TopUnresolvedFiles {
			cmd.Printf("    %4d  %s\n", fc.Count, fc.Path)
		}
	}
}
