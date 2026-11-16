package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"kb-core-ui/internal/memory"
)

// memoryDBPath is the vector-memory DB for a repo. It's a SEPARATE file from
// the code graph (graph.db): the graph is derived from source and gets
// rebuilt freely, but memory is hand/bot-authored knowledge that must
// persist across re-indexing.
func memoryDBPath(root string) string {
	return filepath.Join(root, ".kb-core-ui", "memory.db")
}

func openMemory(repoRoot string) (*memory.Store, error) {
	if err := os.MkdirAll(filepath.Join(repoRoot, ".kb-core-ui"), 0o755); err != nil {
		return nil, err
	}
	// EmbedderFromEnv picks a neural embedder if KB_CORE_UI_EMBED_URL is set,
	// else the offline lexical default.
	return memory.Open(memoryDBPath(repoRoot), memory.EmbedderFromEnv())
}

func newMemoryCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "memory",
		Short: "Vector memory: store & semantically search codebase rules, lessons, business logic",
		Long: `kb-core-ui's vector memory holds non-code knowledge — primary codebase
rules, lessons learned, business-logic/data-dependency notes, and what the
software does — as embeddings you can search semantically. It's the
counterpart to the code graph: the graph answers "where does this code
live", memory answers "what do we know that isn't in the code". Kept in
<repo>/.kb-core-ui/memory.db, separate from the graph so re-indexing never
wipes it.`,
	}
	cmd.AddCommand(newMemoryAddCmd())
	cmd.AddCommand(newMemorySearchCmd())
	cmd.AddCommand(newMemoryListCmd())
	cmd.AddCommand(newMemoryRemoveCmd())
	return cmd
}

func newMemoryAddCmd() *cobra.Command {
	var repoPath, kind, title, text, source, fromFile string
	cmd := &cobra.Command{
		Use:   "add",
		Short: "Add a memory entry",
		Long: `Add a memory entry. Provide --text, or --from-file to read the body from
a file (or '-' for stdin). Kind is one of: rule, lesson, business,
overview, reference.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			if title == "" {
				return fmt.Errorf("--title is required")
			}
			body := text
			if fromFile != "" {
				var data []byte
				if fromFile == "-" {
					data, err = io.ReadAll(os.Stdin)
				} else {
					data, err = os.ReadFile(fromFile)
				}
				if err != nil {
					return err
				}
				body = string(data)
			}
			if body == "" {
				return fmt.Errorf("provide --text or --from-file")
			}
			if !validKind(kind) {
				return fmt.Errorf("invalid --kind %q (want: rule|lesson|business|overview|reference)", kind)
			}

			s, err := openMemory(repoRoot)
			if err != nil {
				return err
			}
			defer s.Close()

			e, err := s.Add(memory.Kind(kind), title, body, source, time.Now())
			if err != nil {
				return err
			}
			cmd.Printf("Added memory %s (%s)\n", e.ID, e.Kind)
			return nil
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "repo the memory belongs to")
	cmd.Flags().StringVar(&kind, "kind", "lesson", "rule | lesson | business | overview | reference")
	cmd.Flags().StringVar(&title, "title", "", "short title (required)")
	cmd.Flags().StringVar(&text, "text", "", "the memory body")
	cmd.Flags().StringVar(&source, "source", "", "where this came from (person, file, url, bot)")
	cmd.Flags().StringVar(&fromFile, "from-file", "", "read the body from a file, or '-' for stdin")
	return cmd
}

func newMemorySearchCmd() *cobra.Command {
	var repoPath, kind string
	var k int
	cmd := &cobra.Command{
		Use:   "search <query>",
		Short: "Semantically search memory for the entries most relevant to a query",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			s, err := openMemory(repoRoot)
			if err != nil {
				return err
			}
			defer s.Close()

			hits, err := s.Search(args[0], memory.Kind(kind), k)
			if err != nil {
				return err
			}
			if len(hits) == 0 {
				cmd.Println("No relevant memory found.")
				return nil
			}
			for _, h := range hits {
				cmd.Printf("\n[%.2f] %s  (%s)\n  %s\n  id: %s\n", h.Score, h.Title, h.Kind, truncate(h.Text, 200), h.ID)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "repo to search")
	cmd.Flags().StringVar(&kind, "kind", "", "restrict to a kind (optional)")
	cmd.Flags().IntVar(&k, "top", 5, "max results")
	return cmd
}

func newMemoryListCmd() *cobra.Command {
	var repoPath, kind string
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List memory entries (newest first)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			s, err := openMemory(repoRoot)
			if err != nil {
				return err
			}
			defer s.Close()

			entries, err := s.List(memory.Kind(kind))
			if err != nil {
				return err
			}
			if len(entries) == 0 {
				cmd.Println("No memory entries yet. Add one with `kb-core-ui memory add`.")
				return nil
			}
			for _, e := range entries {
				cmd.Printf("%-10s  %s\n  %s\n", e.Kind, e.Title, e.ID)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "repo to list")
	cmd.Flags().StringVar(&kind, "kind", "", "restrict to a kind (optional)")
	return cmd
}

func newMemoryRemoveCmd() *cobra.Command {
	var repoPath string
	cmd := &cobra.Command{
		Use:   "rm <id>",
		Short: "Remove a memory entry by id",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			s, err := openMemory(repoRoot)
			if err != nil {
				return err
			}
			defer s.Close()

			ok, err := s.Remove(args[0])
			if err != nil {
				return err
			}
			if !ok {
				return fmt.Errorf("no memory with id %q", args[0])
			}
			cmd.Printf("Removed %s\n", args[0])
			return nil
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "repo the memory belongs to")
	return cmd
}

func validKind(k string) bool {
	switch memory.Kind(k) {
	case memory.KindRule, memory.KindLesson, memory.KindBusiness, memory.KindOverview, memory.KindRef:
		return true
	}
	return false
}

// truncate collapses whitespace (so a multi-line body prints as one tidy
// line) and caps the length for list/search output.
func truncate(s string, n int) string {
	s = strings.Join(strings.Fields(s), " ")
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
