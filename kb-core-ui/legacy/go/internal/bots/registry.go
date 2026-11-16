// Package bots defines the bot roster and a runner that executes bots and
// tracks their runs, backing the CLI's `kb-core-ui bot` commands and the web
// dashboard. Bots are executed by re-invoking this same kb-core-ui binary
// (`kb-core-ui bot <name> ...`), so the CLI and web paths run identical code.
package bots

// ArgDef declares one input a bot accepts, so the dashboard can render a
// form and the runner can validate before starting.
type ArgDef struct {
	Name        string `json:"name"`
	Label       string `json:"label"`
	Required    bool   `json:"required"`
	Placeholder string `json:"placeholder,omitempty"`
	// Bool marks a flag-style boolean arg: passed as "--name" when truthy
	// and omitted otherwise, rather than "--name value".
	Bool bool `json:"bool,omitempty"`
}

// Def is a bot's static definition (mirrors API_CONTRACT.md's BotDef).
type Def struct {
	Name        string   `json:"name"`
	Title       string   `json:"title"`
	Description string   `json:"description"`
	Kind        string   `json:"kind"`      // "go-native" | "python"
	NeedsAuth   bool     `json:"needsAuth"` // needs a working claude session
	Args        []ArgDef `json:"args"`

	// subcommand is how this bot is invoked as `kb-core-ui bot <subcommand>`.
	// Positional args are appended in argOrder; flag args are passed as
	// --name value. Kept unexported — it's an execution detail, not API.
	subcommand string
	// positional lists ArgDef names passed positionally (in order) rather
	// than as flags. Everything else is passed as --name value.
	positional []string
}

// Registry is the built-in bot roster. Order here is the display order.
var Registry = []Def{
	{
		Name:        "doctor",
		Title:       "Doctor",
		Description: "Preflight: verify the whole orchestration chain — python, gh, claude, and kb-core-ui's MCP server all connect.",
		Kind:        "go-native", // it shells to python, but from the UI's view it needs no args and no auth
		NeedsAuth:   false,
		subcommand:  "doctor",
	},
	{
		Name:        "graph-sync",
		Title:       "Graph Sync",
		Description: "Re-index the code graph and check its integrity (dangling edges, resolution quality). No AI, no auth.",
		Kind:        "go-native",
		NeedsAuth:   false,
		subcommand:  "graph-sync",
	},
	{
		Name:        "pr-review",
		Title:       "PR Review",
		Description: "Review an open PR's diff for breaking changes, quality, duplication, rewrites, pattern-mismatch, and cross-boundary contract mismatches. Posts a comment (or use dry-run).",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "pr_number", Label: "PR number", Required: true, Placeholder: "e.g. 12"},
			{Name: "dry_run", Label: "Dry run (print instead of posting)", Required: false, Bool: true},
		},
		subcommand: "pr-review",
		positional: []string{"pr_number"},
	},
	{
		Name:        "commit-check",
		Title:       "Commit Check",
		Description: "Review a single commit's diff (same dimensions as PR review) — run after committing, before pushing.",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "ref", Label: "Commit ref", Required: false, Placeholder: "HEAD"},
		},
		subcommand: "commit-check",
		positional: []string{"ref"},
	},
	{
		Name:        "test-writer",
		Title:       "Test Writer",
		Description: "Generate test cases for a function or file, using the graph to cover real callers and edge cases. Prints tests (add 'true' to write the file).",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "target", Label: "Symbol or file", Required: true, Placeholder: "e.g. BuildFlat or internal/graph/builder.go"},
			{Name: "write", Label: "Write file to disk", Required: false, Bool: true},
		},
		subcommand: "test-writer",
		positional: []string{"target"},
	},
	{
		Name:        "anomaly-scan",
		Title:       "Anomaly Detector",
		Description: "Scan the whole codebase for anomalies: possible breakages, cross-boundary contract mismatches, duplication, and rule violations (from memory).",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "focus", Label: "Focus area (optional)", Required: false, Placeholder: "e.g. the server package"},
		},
		subcommand: "anomaly-scan",
	},
	{
		Name:        "feature-verdict",
		Title:       "Feature Verdict",
		Description: "Plan a proposed feature against this codebase: rules it might break, code to reuse, optimal options, a PRD, and tests to keep current behavior safe.",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "feature", Label: "Feature description", Required: true, Placeholder: "e.g. add a REST endpoint to delete a symbol"},
		},
		subcommand: "feature-verdict",
		positional: []string{"feature"},
	},
	{
		Name:        "triage",
		Title:       "Support Triage",
		Description: "Correlate a GitHub issue to the code via the graph + memory and suggest fixes with file:line references. (Intercom source planned — needs auth.)",
		Kind:        "python",
		NeedsAuth:   true,
		Args: []ArgDef{
			{Name: "issue", Label: "GitHub issue number", Required: true, Placeholder: "e.g. 7"},
			{Name: "comment", Label: "Post as issue comment", Required: false, Bool: true},
		},
		subcommand: "triage",
		positional: []string{"issue"},
	},
}

// Lookup returns the bot definition for name, or ok=false.
func Lookup(name string) (Def, bool) {
	for _, d := range Registry {
		if d.Name == name {
			return d, true
		}
	}
	return Def{}, false
}
