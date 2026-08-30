package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/spf13/cobra"

	"kb-core-ui/internal/bots"
)

// locateBotsDir finds the bots/ directory the same way locateWebDir finds
// web/dist: next to the installed binary, in the current working
// directory, or in this source tree during local development.
func locateBotsDir(explicit string) (string, error) {
	if explicit != "" {
		return explicit, nil
	}
	var candidates []string
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "bots"))
	}
	if wd, err := os.Getwd(); err == nil {
		candidates = append(candidates, filepath.Join(wd, "bots"))
	}
	if _, thisFile, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Join(filepath.Dir(filepath.Dir(filepath.Dir(thisFile))), "bots"))
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			return c, nil
		}
	}
	return "", fmt.Errorf("bots/ directory not found (looked next to the binary, in cwd, and in the kb-core-ui source tree) — pass --bots-dir")
}

func newBotCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "bot",
		Short: "Run an AI bot (see bots/README.md for the full list)",
	}
	cmd.AddCommand(newBotDoctorCmd())
	cmd.AddCommand(newBotGraphSyncCmd())
	cmd.AddCommand(newBotPRReviewCmd())

	// The remaining Python bots do their own argument parsing, so they're
	// registered as thin passthroughs that forward everything to the
	// script. Metadata comes from the shared registry so the CLI and the
	// web dashboard list exactly the same bots.
	passthrough := map[string]string{
		"commit-check":    "commit_check.py",
		"test-writer":     "test_writer.py",
		"anomaly-scan":    "anomaly_scan.py",
		"feature-verdict": "feature_verdict.py",
		"triage":          "triage.py",
	}
	for _, def := range bots.Registry {
		script, ok := passthrough[def.Name]
		if !ok {
			continue
		}
		cmd.AddCommand(newBotPassthroughCmd(def.Name, script, def.Description))
	}
	return cmd
}

// newBotPassthroughCmd builds a `kb-core-ui bot <name>` command that forwards
// all args to the bot's Python script (which does its own arg parsing),
// injecting --repo <cwd> when the caller didn't pass one.
func newBotPassthroughCmd(name, script, short string) *cobra.Command {
	return &cobra.Command{
		Use:                name + " [args...]",
		Short:              short,
		DisableFlagParsing: true, // let the Python script parse its own flags
		RunE: func(cmd *cobra.Command, args []string) error {
			if !hasRepoFlag(args) {
				wd, err := os.Getwd()
				if err != nil {
					return err
				}
				args = append(args, "--repo", wd)
			}
			return runBotScript(script, "", args)
		},
	}
}

func hasRepoFlag(args []string) bool {
	for _, a := range args {
		if a == "--repo" || strings.HasPrefix(a, "--repo=") {
			return true
		}
	}
	return false
}

// runBotScript execs a bots/*.py script, forwarding stdio and propagating
// its exit code, so `kb-core-ui bot X` behaves like running the script
// directly. Shared by every bot subcommand.
func runBotScript(scriptName string, botsDir string, pyArgs []string) error {
	bots, err := locateBotsDir(botsDir)
	if err != nil {
		return err
	}
	script := filepath.Join(bots, scriptName)
	if _, err := os.Stat(script); err != nil {
		return fmt.Errorf("bot script not found at %s: %w", script, err)
	}
	python := exec.Command("python3", append([]string{script}, pyArgs...)...)
	python.Stdout = os.Stdout
	python.Stderr = os.Stderr
	python.Stdin = os.Stdin
	if err := python.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		return err
	}
	return nil
}

func newBotDoctorCmd() *cobra.Command {
	var repoPath, botsDir, kbCoreUIBin string
	cmd := &cobra.Command{
		Use:   "doctor",
		Short: "Verify the orchestration chain: claude connects, gh authed, MCP server responds",
		Long: `Runs preflight checks for the whole bot orchestration:
python, the gh CLI (installed + authenticated), the claude CLI (installed +
able to actually get a completion), and kb-core-ui's own MCP server (does it
respond with its tools). Use this to confirm "our app can connect a Claude
session from the terminal" before running any bot.`,
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			pyArgs := []string{"--repo", repoRoot}
			if kbCoreUIBin != "" {
				pyArgs = append(pyArgs, "--kb-core-ui-bin", kbCoreUIBin)
			}
			return runBotScript("preflight.py", botsDir, pyArgs)
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "path to the local repo checkout")
	cmd.Flags().StringVar(&botsDir, "bots-dir", "", "path to the bots/ directory (default: auto-detect)")
	cmd.Flags().StringVar(&kbCoreUIBin, "kb-core-ui-bin", "", "path to the kb-core-ui binary (default: auto-detect)")
	return cmd
}

func newBotPRReviewCmd() *cobra.Command {
	var repoPath, botsDir, kbCoreUIBin string
	var dryRun bool
	cmd := &cobra.Command{
		Use:   "pr-review <pr-number>",
		Short: "Review an open PR's diff and post findings as a comment",
		Long: `Reviews an open GitHub PR's diff with Claude, using kb-core-ui's own MCP
server as the model's source of repo context (search the code graph,
don't read whole files), then posts the findings as a PR comment.

Requires: gh (authenticated), claude (authenticated — a local
` + "`claude login`" + ` session, or ANTHROPIC_API_KEY in CI), and a kb-core-ui
binary (this one, or one found on PATH).`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath([]string{repoPath})
			if err != nil {
				return err
			}
			pyArgs := []string{args[0], "--repo", repoRoot}
			if kbCoreUIBin != "" {
				pyArgs = append(pyArgs, "--kb-core-ui-bin", kbCoreUIBin)
			}
			if dryRun {
				pyArgs = append(pyArgs, "--dry-run")
			}
			return runBotScript("pr_review.py", botsDir, pyArgs)
		},
	}
	cmd.Flags().StringVar(&repoPath, "repo", ".", "path to the local repo checkout")
	cmd.Flags().StringVar(&botsDir, "bots-dir", "", "path to the bots/ directory (default: auto-detect)")
	cmd.Flags().StringVar(&kbCoreUIBin, "kb-core-ui-bin", "", "path to the kb-core-ui binary (default: auto-detect)")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "print the review instead of posting it as a PR comment")
	return cmd
}
