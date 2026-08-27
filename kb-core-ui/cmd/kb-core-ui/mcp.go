package main

import (
	"os"

	mcpserver "github.com/mark3labs/mcp-go/server"
	"github.com/spf13/cobra"

	"kb-core-ui/internal/mcp"
)

func newMCPCmd() *cobra.Command {
	var dbPath string
	cmd := &cobra.Command{
		Use:   "mcp [path]",
		Short: "Parse a repo and run an MCP server over stdio for AI agents",
		Long: `Runs an MCP server speaking JSON-RPC over stdio, exposing the code graph
(search_symbol, get_symbol, get_file_symbols, get_callers, get_callees,
get_file_slice, get_tree, get_stats) AND the vector memory (memory_search,
memory_add) so an AI agent can query the graph instead of reading whole
files, and recall the codebase's rules and lessons. Point an MCP-capable
client at "kb-core-ui mcp <path>" as the command to launch.`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			// stdio IS the MCP transport — nothing but the protocol may
			// touch stdout, so redirect all progress/log output to stderr.
			cmd.SetOut(os.Stderr)

			repoRoot, err := resolveRepoPath(args)
			if err != nil {
				return err
			}
			s, err := openStoreAndIndex(cmd, repoRoot, dbPath)
			if err != nil {
				return err
			}
			defer s.Close()

			// Memory is best-effort: if it can't open, the graph tools
			// still serve. mem == nil simply omits the memory_* tools.
			mem, err := openMemory(repoRoot)
			if err != nil {
				cmd.Printf("memory unavailable (%v) — serving graph tools only\n", err)
				mem = nil
			}
			if mem != nil {
				defer mem.Close()
			}

			srv := mcp.New(s, repoRoot, mem)
			return mcpserver.ServeStdio(srv)
		},
	}
	cmd.Flags().StringVar(&dbPath, "db", "", "path to the SQLite graph DB (default: <repo>/.kb-core-ui/graph.db)")
	return cmd
}
