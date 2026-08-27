// Command kb-core-ui parses a source repo into a code knowledge graph and
// serves it as a visual debugger (web UI) and/or an MCP server for AI
// agents.
package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

func main() {
	root := &cobra.Command{
		Use:   "kb-core-ui",
		Short: "AI Code Knowledge Graph & Visual Debugger",
		Long: `kb-core-ui parses a source repo (Go, TypeScript, JavaScript, Python) into a
symbol/call graph — functions, classes, methods, consts, vars, with types,
call edges, and file:line references — stored locally in SQLite under
.kb-core-ui/. It's a companion for both humans (a visual graph explorer) and
AI agents (an MCP server exposing search/get_symbol/get_callers/get_callees
tools) so debugging AI-written code means tracing the graph instead of
re-reading the whole codebase.`,
	}

	root.AddCommand(newParseCmd())
	root.AddCommand(newServeCmd())
	root.AddCommand(newMCPCmd())
	root.AddCommand(newBotCmd())
	root.AddCommand(newMemoryCmd())

	if err := root.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, "kb-core-ui:", err)
		os.Exit(1)
	}
}
