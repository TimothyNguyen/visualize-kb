package main

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"runtime"

	"github.com/spf13/cobra"

	"kb-core-ui/internal/bots"
	"kb-core-ui/internal/server"
)

func newServeCmd() *cobra.Command {
	var dbPath, webDir string
	var port int
	var open bool
	cmd := &cobra.Command{
		Use:   "serve [path]",
		Short: "Parse a repo and serve the graph API + web visualizer",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath(args)
			if err != nil {
				return err
			}
			s, err := openStoreAndIndex(cmd, repoRoot, dbPath)
			if err != nil {
				return err
			}
			defer s.Close()

			resolvedWebDir := locateWebDir(webDir)
			if resolvedWebDir == "" {
				cmd.Println("No built web UI found (looked for web/dist). Serving the API only — see API_CONTRACT.md, or pass --web-dir.")
			}

			// The bot runner re-invokes this same kb-core-ui binary, so the
			// web dashboard runs the exact same code paths as the CLI. If
			// we can't resolve our own path, the dashboard's run endpoints
			// are simply disabled (nil runner) — the graph UI still works.
			var runner *bots.Runner
			if self, err := os.Executable(); err == nil {
				runner = bots.NewRunner(self, repoRoot)
			} else {
				cmd.Println("Could not resolve the kb-core-ui binary path — bot dashboard disabled, graph UI still available.")
			}

			// Memory is best-effort too: nil just omits the memory endpoints.
			mem, err := openMemory(repoRoot)
			if err != nil {
				cmd.Printf("Memory unavailable (%v) — serving without the memory tab.\n", err)
				mem = nil
			}
			if mem != nil {
				defer mem.Close()
			}

			srv := server.New(s, repoRoot, resolvedWebDir, runner, mem)
			addr := fmt.Sprintf("localhost:%d", port)
			url := "http://" + addr

			cmd.Printf("kb-core-ui serving %s\n", url)
			if open {
				openBrowser(url)
			}
			return http.ListenAndServe(addr, srv)
		},
	}
	cmd.Flags().StringVar(&dbPath, "db", "", "path to the SQLite graph DB (default: <repo>/.kb-core-ui/graph.db)")
	cmd.Flags().StringVar(&webDir, "web-dir", "", "path to the built web UI (web/dist); auto-detected if omitted")
	cmd.Flags().IntVar(&port, "port", 8420, "port to listen on")
	cmd.Flags().BoolVar(&open, "open", true, "open the web UI in a browser on start")
	return cmd
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		cmd = exec.Command("open", url)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	_ = cmd.Start()
}
