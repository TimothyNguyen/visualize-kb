# T13 handoff: default-runtime switch and the legacy Go move

Written for whoever picks up SPEC.md T13 — the last open task in the
Go-to-Python migration. T1–T12 are done and committed on
`codex/go-to-python-migration`.

This is a runbook, not prose. It is deliberately in plain English rather than
the caveman notation SPEC.md uses: the sequence is destructive and order
matters, and compression here buys nothing worth the ambiguity.

## What T13 is

> Switch the default runtime to Python; move the Go module to
> `kb-core-ui/legacy/go/` read-only; keep the legacy oracle runnable for the
> harness. (V10, V11)

## Precondition — do not skip this

**C7 forbids the move until the CI parity gate has actually passed.**

`.github/workflows/parity.yml` was added in T12 and *has never run*. Local
parity is 104/104, but V10 names CI as the gate, not a developer's machine.
Before touching anything:

1. Push `codex/go-to-python-migration`.
2. Watch the `parity` job. It must be green, including the `Go vs Python
   parity` step reporting `failed=0 errored=0`.
3. Only then proceed.

If CI fails, that is the task — fix the divergence, not the workflow. The
likely first-run failures are environment-shaped, not port bugs; see
"Expected CI first-run friction" below.

## The trap that will silently break parity

Read this before writing any code.

`kb-core-ui/python/pyproject.toml` declares a console script:

```toml
[project.scripts]
kb-core-ui = "kb_core_ui.__main__:main"
```

So `pip install -e ./python` puts an executable named **`kb-core-ui`** on
PATH. Meanwhile `harness/harness/engines.py::resolve_go_binary` falls back to:

```python
found = shutil.which("kb-core-ui")
```

After the Go binary stops living at `kb-core-ui/kb-core-ui`, that fallback
will find **the Python entry point** and hand it back as the *Go oracle*.
Parity then compares Python against Python, reports a perfect score, and
proves nothing. Nothing in the current harness would catch this.

**Required:** before moving anything, make `resolve_go_binary` refuse a
non-Go binary rather than guess. Two defensible options:

- Drop the `shutil.which` fallback entirely and resolve only from the
  new `legacy/go/` build output plus `$KB_CORE_UI_BIN`. Simplest, and the
  harness always builds the oracle anyway.
- Keep a fallback but verify the candidate is the Go build — e.g. run it with
  a flag the Python port does not implement, or check it is not a Python
  console script.

Prefer the first. Then add a harness test asserting that a `kb-core-ui` on
PATH is *not* accepted as the Go engine.

## Step-by-step

### 1. Guard the oracle resolution (before the move)

Edit `harness/harness/engines.py::resolve_go_binary` per the trap above.
Update its error message — `harness/tests/conftest.py:20` and
`harness/tests/test_engines_templating.py:53` both assert on the current
`go build` wording, so they will need updating in step 4.

### 2. Move the Go module

The module path is plain `kb-core-ui` (not a URL), and every internal import
is `kb-core-ui/internal/...`. Because the module is self-contained, **moving
`go.mod`, `go.sum`, `cmd/` and `internal/` together requires no import
rewrites at all.** Do not renumber the module path; that would be churn for
no benefit and would break V11's "complete runnable module".

```
git mv kb-core-ui/go.mod      kb-core-ui/legacy/go/go.mod
git mv kb-core-ui/go.sum      kb-core-ui/legacy/go/go.sum
git mv kb-core-ui/cmd         kb-core-ui/legacy/go/cmd
git mv kb-core-ui/internal    kb-core-ui/legacy/go/internal
```

Leave `bots/`, `web/`, `python/`, `harness/` where they are. They are not
part of the Go module.

Verify immediately:

```
cd kb-core-ui/legacy/go && go build ./... && go test ./...
```

`internal/server TestBotsEndpoints` fails on Windows for a pre-existing,
unrelated reason (it writes a `#!/bin/sh` script named `fake-kb-core-ui` with
no `.exe` extension and execs it). It passes on Linux. Do not "fix" this as
part of T13.

### 3. Point the harness at the new location

`resolve_go_binary` currently derives the repo root as
`Path(__file__).resolve().parents[2]` — that is `kb-core-ui/`. It must become
`kb-core-ui/legacy/go/`. Note it checks both `kb-core-ui.exe` and
`kb-core-ui`, so the build output name can stay the same.

Add a comment explaining *why* the oracle lives under `legacy/` — C6 keeps it
runnable for regression comparison; it is archived, not deleted.

### 4. Update every build instruction

Search for the old command and fix each occurrence:

```
grep -rn 'go build -o kb-core-ui' --include='*.md' --include='*.yml' --include='*.py' .
```

Known sites:

| File | Note |
|---|---|
| `.github/workflows/parity.yml` | the live gate — must build from `legacy/go` |
| `kb-core-ui/harness/README.md` | dev instructions |
| `kb-core-ui/harness/tests/conftest.py:20` | error-message assertion |
| `kb-core-ui/harness/tests/test_engines_templating.py:53` | asserts on `"go build"` |
| `kb-core-ui/bots/common.py:64-67` | `find_kb_core_ui_bin` error text |
| `kb-core-ui/.github/workflows/*.yml` | **inert** — see below |

`kb-core-ui/.github/workflows/` holds two workflows left over from when
`kb-core-ui` was its own repository. GitHub only reads `.github/` at the
repository root, so they do not run here (SPEC.md B13). Decide deliberately:
update them for consistency, or delete them as dead weight. Do not promote
them to the root without checking what they would start doing — the PR review
bot spends API credits.

### 5. Switch the default runtime

"Default" concretely means: **what `bots/common.py::find_kb_core_ui_bin`
returns.** That function's result is used two ways — as argv[0] for
`kb-core-ui parse`, and as the `command` in the generated Claude MCP config
(`build_mcp_config`, `common.py:76`).

Current precedence:

1. explicit `--kb-core-ui-bin`
2. `kb-core-ui/kb-core-ui` (the Go build output)
3. `shutil.which("kb-core-ui")`

After the move, step 2 no longer exists, so the Python console script wins by
default. **Do not leave that to accident.** Make it explicit: resolve the
Python entry point deliberately, and keep an opt-in escape hatch (an env var
or flag) for running the Go oracle instead. The MCP config consumer needs a
single executable path, which the console script satisfies — so this stays a
`str`, no signature change.

Add a test covering the precedence, because the failure mode (silently
running the wrong runtime) is invisible.

### 6. Update the docs

`kb-core-ui/README.md`, `kb-core-ui/harness/README.md`, `bots/README.md`, and
`ORCHESTRATION.md` describe a Go program. At minimum: how to install the
Python runtime, where the Go oracle now lives, and that it is retained for
parity rather than for use.

### 7. Update SPEC.md

Mark T13 `x`. Add a `§B` row for anything that bit you. If the PATH-shadowing
trap above turns out to be real in practice, it deserves one.

## Verification — all of it, in this order

```
cd kb-core-ui/legacy/go && go build -o ../../kb-core-ui.exe ./cmd/kb-core-ui && go test ./...
cd kb-core-ui/python    && python -m pytest -q       # expect 68 passed
cd kb-core-ui/harness   && python -m pytest -q       # expect 122 passed
cd kb-core-ui/harness   && python -m harness parity --oracle go --candidate python
cd kb-core-ui/harness   && python -m harness verify
```

Parity and verify must both report `passed=104 failed=0 errored=0`.

**Prove the oracle is really Go.** After the move, deliberately confirm the
harness is not running Python on both sides — for example, break something in
`legacy/go/internal/server` and check that parity *fails*. A green run is
only meaningful if it can go red.

`verify` is a local check only; it replays baselines recorded on Windows and
some values are platform-specific (SPEC.md B11, V12). Do not add it to CI.

## Expected CI first-run friction

The parity workflow has never executed. Anticipate:

- **`.js` Content-Type.** Go and Python both read the OS mime table, so a
  `.js` asset is `application/javascript` on Windows and likely
  `text/javascript; charset=utf-8` on Linux. Both engines should still agree
  with *each other*, which is all parity asks. If they do not, the fix is in
  `python/kb_core_ui/server/app.py::_content_type`, which mirrors Go's rule of
  appending `charset=utf-8` to `text/*` types lacking one (B11).
- **Grammar versions.** Pinned exactly in `python/pyproject.toml` (B14). If a
  parser diff appears, check the pins against
  `github.com/smacker/go-tree-sitter` in the Go module before suspecting the
  port.
- **`go test ./...` passing on Linux** where it fails on Windows, per step 2.

## Rollback

Everything is one commit per task on a branch. If the move goes wrong,
`git revert` the T13 commit — the Go module is moved, never deleted, so
nothing is lost. Do not delete `legacy/go/`: C6 and V11 require it to stay
complete and runnable.

## Do not

- Do not perform the move before CI parity is observed green (C7).
- Do not delete or trim the Go module. It is the oracle.
- Do not rewrite Go import paths. Moving the module wholesale needs none.
- Do not add `verify` to CI.
- Do not "fix" the Windows-only `TestBotsEndpoints` failure here.
