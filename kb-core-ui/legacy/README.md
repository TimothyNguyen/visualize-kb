# Legacy Go oracle

`go/` contains the complete, unchanged Go module archived by spec/SPEC.md T13.
Treat its source as read-only (C6). Implement runtime changes in `../python/`.
The module path and imports remain `kb-core-ui`; do not rewrite them.

The cutover prerequisite passed in CI at `bbad0ff235d6ace5a66c4a7c1e7229a468de986d`:
https://github.com/TimothyNguyen/visualize-kb/actions/runs/33212177435
The parity step reported `passed=104 failed=0 errored=0`.

## Build and test

From `kb-core-ui/legacy/go/`:

```sh
go build -o kb-core-ui ./cmd/kb-core-ui
go test ./...
```

On Windows use `-o kb-core-ui.exe`. Keep build outputs here, not at
`kb-core-ui/`. The known Windows-only `TestBotsEndpoints` failure uses a
POSIX shell fixture; the unchanged suite passes on Linux CI.

The harness resolves only this directory, `--go-bin`, or `KB_CORE_UI_BIN`.
Explicit overrides must name a real Go build. It never searches PATH, where
the Python console script has the same name. For legacy bot runs, pass
`--kb-core-ui-bin` with the absolute path to this Go executable. When running
the oracle outside the source root, pass `--bots-dir` and `--web-dir` as needed.

## Rollback

Revert the T13 cutover commit if it has been committed. Before committing,
restore only T13 changes and move `go.mod`, `go.sum`, `cmd/`, and `internal/`
back to `kb-core-ui/`. Preserve unrelated working tree changes. Never delete
the archived module or database files; both runtimes use the existing schema.
