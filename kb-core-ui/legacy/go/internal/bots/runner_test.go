package bots

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

// fakeBin writes a tiny shell script that echoes its args and exits with a
// controllable code, standing in for the real kb-core-ui binary so the runner
// is tested hermetically (no kb-core-ui/claude needed).
func fakeBin(t *testing.T, exitCode int) string {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("fake bin uses a POSIX shell script")
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "fake-kb-core-ui")
	script := "#!/bin/sh\necho \"args: $@\"\nexit " + itoa(exitCode) + "\n"
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	return string(rune('0' + i))
}

func waitDone(t *testing.T, r *Runner, id string) *Run {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		run, ok := r.Get(id)
		if !ok {
			t.Fatalf("run %s vanished", id)
		}
		if run.Status != "running" {
			return run
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("run %s did not finish in time", id)
	return nil
}

func TestRunnerSucceeds(t *testing.T) {
	r := NewRunner(fakeBin(t, 0), t.TempDir())
	run, err := r.Start("graph-sync", nil)
	if err != nil {
		t.Fatal(err)
	}
	if run.Status != "running" {
		t.Fatalf("expected initial status running, got %s", run.Status)
	}
	done := waitDone(t, r, run.ID)
	if done.Status != "succeeded" {
		t.Fatalf("expected succeeded, got %s (output: %q)", done.Status, done.Output)
	}
	if done.ExitCode == nil || *done.ExitCode != 0 {
		t.Fatalf("expected exit 0, got %v", done.ExitCode)
	}
	// The bot's argv should include the subcommand and the --repo flag.
	if want := "bot graph-sync"; !contains(done.Output, want) {
		t.Fatalf("expected output to contain %q, got %q", want, done.Output)
	}
	if !contains(done.Output, "--repo") {
		t.Fatalf("expected --repo in args, got %q", done.Output)
	}
}

func TestRunnerFailPropagatesExitCode(t *testing.T) {
	r := NewRunner(fakeBin(t, 2), t.TempDir())
	run, err := r.Start("graph-sync", nil)
	if err != nil {
		t.Fatal(err)
	}
	done := waitDone(t, r, run.ID)
	if done.Status != "failed" {
		t.Fatalf("expected failed, got %s", done.Status)
	}
	if done.ExitCode == nil || *done.ExitCode != 2 {
		t.Fatalf("expected exit 2, got %v", done.ExitCode)
	}
}

func TestRunnerRejectsUnknownBot(t *testing.T) {
	r := NewRunner(fakeBin(t, 0), t.TempDir())
	_, err := r.Start("does-not-exist", nil)
	if _, ok := err.(ErrUnknownBot); !ok {
		t.Fatalf("expected ErrUnknownBot, got %v", err)
	}
}

func TestRunnerRequiresRequiredArg(t *testing.T) {
	r := NewRunner(fakeBin(t, 0), t.TempDir())
	// pr-review requires pr_number.
	_, err := r.Start("pr-review", nil)
	if _, ok := err.(ErrMissingArg); !ok {
		t.Fatalf("expected ErrMissingArg, got %v", err)
	}
}

func TestBuildArgsPositionalAndFlags(t *testing.T) {
	def, _ := Lookup("pr-review")
	args, err := buildArgs(def, map[string]string{"pr_number": "12", "dry_run": "true"}, "/repo")
	if err != nil {
		t.Fatal(err)
	}
	// Expect: bot pr-review 12 --dry-run --repo /repo
	want := []string{"bot", "pr-review", "12", "--dry-run", "--repo", "/repo"}
	if len(args) != len(want) {
		t.Fatalf("arg count mismatch: got %v want %v", args, want)
	}
	for i := range want {
		if args[i] != want[i] {
			t.Fatalf("arg %d: got %q want %q (full: %v)", i, args[i], want[i], args)
		}
	}
}

func TestBuildArgsDryRunFalseOmitsFlag(t *testing.T) {
	def, _ := Lookup("pr-review")
	args, _ := buildArgs(def, map[string]string{"pr_number": "5", "dry_run": "false"}, "/repo")
	for _, a := range args {
		if a == "--dry-run" {
			t.Fatalf("did not expect --dry-run when dry_run=false, got %v", args)
		}
	}
}

func TestListNewestFirst(t *testing.T) {
	r := NewRunner(fakeBin(t, 0), t.TempDir())
	r1, _ := r.Start("graph-sync", nil)
	waitDone(t, r, r1.ID)
	r2, _ := r.Start("doctor", nil)
	waitDone(t, r, r2.ID)

	list := r.List()
	if len(list) != 2 {
		t.Fatalf("expected 2 runs, got %d", len(list))
	}
	if list[0].ID != r2.ID {
		t.Fatalf("expected newest run (%s) first, got %s", r2.ID, list[0].ID)
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && (indexOf(haystack, needle) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

func TestBuildArgsNewBots(t *testing.T) {
	cases := []struct {
		bot  string
		args map[string]string
		want []string
	}{
		{"commit-check", map[string]string{"ref": "HEAD~1"}, []string{"bot", "commit-check", "HEAD~1", "--repo", "/r"}},
		{"commit-check", map[string]string{}, []string{"bot", "commit-check", "", "--repo", "/r"}},
		{"test-writer", map[string]string{"target": "BuildFlat", "write": "true"}, []string{"bot", "test-writer", "BuildFlat", "--write", "--repo", "/r"}},
		{"test-writer", map[string]string{"target": "BuildFlat", "write": "false"}, []string{"bot", "test-writer", "BuildFlat", "--repo", "/r"}},
		{"anomaly-scan", map[string]string{"focus": "server"}, []string{"bot", "anomaly-scan", "--focus", "server", "--repo", "/r"}},
		{"anomaly-scan", map[string]string{}, []string{"bot", "anomaly-scan", "--repo", "/r"}},
		{"feature-verdict", map[string]string{"feature": "add delete endpoint"}, []string{"bot", "feature-verdict", "add delete endpoint", "--repo", "/r"}},
		{"triage", map[string]string{"issue": "7", "comment": "true"}, []string{"bot", "triage", "7", "--comment", "--repo", "/r"}},
	}
	for _, c := range cases {
		def, ok := Lookup(c.bot)
		if !ok {
			t.Fatalf("bot %s not in registry", c.bot)
		}
		got, err := buildArgs(def, c.args, "/r")
		if err != nil {
			t.Fatalf("%s: %v", c.bot, err)
		}
		if len(got) != len(c.want) {
			t.Fatalf("%s: got %v want %v", c.bot, got, c.want)
		}
		for i := range c.want {
			if got[i] != c.want[i] {
				t.Fatalf("%s arg %d: got %q want %q (full %v)", c.bot, i, got[i], c.want[i], got)
			}
		}
	}
}
