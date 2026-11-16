package bots

import (
	"bytes"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Run is a single execution of a bot (mirrors API_CONTRACT.md's BotRun).
type Run struct {
	ID         string     `json:"id"`
	Bot        string     `json:"bot"`
	Status     string     `json:"status"` // "running" | "succeeded" | "failed"
	StartedAt  time.Time  `json:"startedAt"`
	FinishedAt *time.Time `json:"finishedAt,omitempty"`
	ExitCode   *int       `json:"exitCode,omitempty"`
	Output     string     `json:"output"`
}

// RunSummary is a Run without its (potentially large) output, for list views.
type RunSummary struct {
	ID         string     `json:"id"`
	Bot        string     `json:"bot"`
	Status     string     `json:"status"`
	StartedAt  time.Time  `json:"startedAt"`
	FinishedAt *time.Time `json:"finishedAt,omitempty"`
	ExitCode   *int       `json:"exitCode,omitempty"`
}

// Runner executes bots by re-invoking the kb-core-ui binary and tracks their
// runs in memory. Safe for concurrent use. Runs are not persisted — this is
// a local dev tool; restarting kb-core-ui clears run history.
type Runner struct {
	selfBin  string // path to the kb-core-ui binary to re-invoke
	repoRoot string

	mu   sync.Mutex
	runs map[string]*Run
	seq  int
	now  func() time.Time // injectable for tests
}

// NewRunner builds a Runner. selfBin is the kb-core-ui executable to invoke
// (`<selfBin> bot <sub> ...`); repoRoot is the repo bots operate on.
func NewRunner(selfBin, repoRoot string) *Runner {
	return &Runner{
		selfBin:  selfBin,
		repoRoot: repoRoot,
		runs:     make(map[string]*Run),
		now:      time.Now,
	}
}

// ErrUnknownBot / ErrMissingArg are returned by Start for bad requests so
// the HTTP layer can map them to 404/400.
type ErrUnknownBot struct{ Name string }

func (e ErrUnknownBot) Error() string { return "unknown bot: " + e.Name }

type ErrMissingArg struct{ Arg string }

func (e ErrMissingArg) Error() string { return "missing required arg: " + e.Arg }

// Start validates args, launches the bot in the background, and returns the
// initial (running) Run immediately. Output accumulates on the Run until it
// finishes; callers poll Get to observe progress.
func (r *Runner) Start(botName string, args map[string]string) (*Run, error) {
	def, ok := Lookup(botName)
	if !ok {
		return nil, ErrUnknownBot{botName}
	}
	for _, a := range def.Args {
		if a.Required && args[a.Name] == "" {
			return nil, ErrMissingArg{a.Name}
		}
	}

	cmdArgs, err := buildArgs(def, args, r.repoRoot)
	if err != nil {
		return nil, err
	}

	r.mu.Lock()
	r.seq++
	id := "run-" + strconv.Itoa(r.seq)
	run := &Run{
		ID:        id,
		Bot:       botName,
		Status:    "running",
		StartedAt: r.now(),
	}
	r.runs[id] = run
	r.mu.Unlock()

	go r.execute(run, cmdArgs)
	return r.snapshot(id), nil
}

// buildArgs turns a bot def + user args into the argv after
// `kb-core-ui bot`. Positional args (declared in def.positional) come first
// in order; the rest become flags — boolean args as "--name" when truthy,
// others as "--name value". Arg names use underscores (JSON-friendly) but
// CLI flags use dashes, so "dry_run" -> "--dry-run". Every bot also gets
// --repo <repoRoot> so it operates on the served repo.
func buildArgs(def Def, args map[string]string, repoRoot string) ([]string, error) {
	byName := map[string]ArgDef{}
	for _, a := range def.Args {
		byName[a.Name] = a
	}

	out := []string{"bot", def.subcommand}
	posSet := map[string]bool{}
	for _, name := range def.positional {
		posSet[name] = true
		out = append(out, args[name]) // positional value (may be empty for optional ones)
	}

	// Deterministic flag order for testability.
	var flagNames []string
	for _, a := range def.Args {
		if posSet[a.Name] || args[a.Name] == "" {
			continue
		}
		flagNames = append(flagNames, a.Name)
	}
	sort.Strings(flagNames)
	for _, name := range flagNames {
		flag := "--" + strings.ReplaceAll(name, "_", "-")
		if byName[name].Bool {
			if isTruthy(args[name]) {
				out = append(out, flag)
			}
			continue
		}
		out = append(out, flag, args[name])
	}
	out = append(out, "--repo", repoRoot)
	return out, nil
}

func isTruthy(s string) bool {
	switch s {
	case "true", "1", "yes", "on":
		return true
	}
	return false
}

func (r *Runner) execute(run *Run, cmdArgs []string) {
	cmd := exec.Command(r.selfBin, cmdArgs...)
	cmd.Dir = r.repoRoot

	// One buffer for combined stdout+stderr, guarded so the polling reader
	// (Get) sees a consistent snapshot while the process writes.
	lw := &lockedWriter{}
	cmd.Stdout = lw
	cmd.Stderr = lw

	// Stream output into the Run as it's produced.
	stop := make(chan struct{})
	go func() {
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				r.mu.Lock()
				run.Output = lw.String()
				r.mu.Unlock()
			case <-stop:
				return
			}
		}
	}()

	err := cmd.Run()
	close(stop)

	exit := 0
	if err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			exit = ee.ExitCode()
		} else {
			exit = -1
			lw.WriteString("\n[runner] failed to execute bot: " + err.Error() + "\n")
		}
	}

	fin := r.now()
	r.mu.Lock()
	run.Output = lw.String()
	run.ExitCode = &exit
	run.FinishedAt = &fin
	if exit == 0 {
		run.Status = "succeeded"
	} else {
		run.Status = "failed"
	}
	r.mu.Unlock()
}

// Get returns a snapshot copy of one run, or ok=false.
func (r *Runner) Get(id string) (*Run, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[id]
	if !ok {
		return nil, false
	}
	return copyRun(run), true
}

func (r *Runner) snapshot(id string) *Run {
	r.mu.Lock()
	defer r.mu.Unlock()
	return copyRun(r.runs[id])
}

// List returns run summaries newest-first.
func (r *Runner) List() []RunSummary {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]RunSummary, 0, len(r.runs))
	for _, run := range r.runs {
		out = append(out, RunSummary{
			ID: run.ID, Bot: run.Bot, Status: run.Status,
			StartedAt: run.StartedAt, FinishedAt: run.FinishedAt, ExitCode: run.ExitCode,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].StartedAt.After(out[j].StartedAt) })
	return out
}

func copyRun(run *Run) *Run {
	c := *run
	if run.FinishedAt != nil {
		t := *run.FinishedAt
		c.FinishedAt = &t
	}
	if run.ExitCode != nil {
		e := *run.ExitCode
		c.ExitCode = &e
	}
	return &c
}

// lockedWriter is an io.Writer + String() accumulator safe for the writer
// goroutine (cmd) and reader goroutine (poller) to share.
type lockedWriter struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (w *lockedWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.buf.Write(p)
}

func (w *lockedWriter) WriteString(s string) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.buf.WriteString(s)
}

func (w *lockedWriter) String() string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.buf.String()
}
