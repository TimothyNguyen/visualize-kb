# KB Core UI Orchestration — Status

The AI engineering-intelligence platform built on top of kb-core-ui's code
graph. This maps every requirement to its concrete, verifiable status.

Python is the default runtime after spec/SPEC.md T13. Install from `kb-core-ui/`
with `python -m pip install -e "./python[dev]"` in an activated environment.
The complete Go module is archived read-only in `legacy/go/` for parity;
see `legacy/README.md` for build instructions and rollback. Bot scripts use
the current interpreter's console entry point; `--kb-core-ui-bin` is the
explicit legacy escape hatch.

Legend: ✅ done & verified · 🔒 blocked on your `claude` login (code complete)

## 0. Foundation — the code graph ✅

| Capability | Where |
|---|---|
| Parse repo into a symbol/call graph (Go, TS, TSX, JS, Python) | `python/kb_core_ui/parser` |
| Top-level symbols only — no library/system internals | `python/kb_core_ui/indexer.py` (skips deps), parsers emit only declared symbols |
| Route-level detection (Go `net/http`) | `python/kb_core_ui/parser/golang.py` |
| Cross-file method→type resolution | `python/kb_core_ui/builder.py` |
| Graph in SQLite, incremental re-index by content hash | `python/kb_core_ui/store.py`, `python/kb_core_ui/indexer.py` |
| MCP server: AI searches the graph instead of reading files | `python/kb_core_ui/mcp` |
| Web graph visualizer | `web/` (React + @xyflow/react) |

## 1. "App can connect a Claude session from the terminal" ✅ / 🔒 credential

Proven and self-verifying. Run:

```sh
kb-core-ui bot doctor
```

It checks the whole chain (python, gh, claude, and kb-core-ui's own MCP
server) and reports each link. On this machine: **5/6 green** — the MCP
server responds with all its tools (the app side works); the one red is the
expired local `claude` login, which only you can refresh (`claude`
interactively, or set `ANTHROPIC_API_KEY`). No code can fix a login.

## 2. Bots — ✅ all 8 built

Run any from the CLI (`kb-core-ui bot <name>`) or the web dashboard. Graph-only
bots need no auth; AI bots preflight-check and fail gracefully until
`claude` auth is present.

| Bot | Does | Auth | Status |
|---|---|---|---|
| **doctor** | preflight: verify the whole chain connects | none | ✅ |
| **graph-sync** | re-index + integrity check (dangling edges, resolution) | none | ✅ verified in CI |
| **pr-review** | review a PR diff: breaks, quality, duplication, rewrites, pattern-mismatch, cross-boundary contract mismatches → posts a comment | claude | ✅ built · 🔒 |
| **commit-check** | same dimensions, per-commit | claude | ✅ built · 🔒 |
| **test-writer** | generate tests for a symbol/file using real callers | claude | ✅ built · 🔒 |
| **anomaly-scan** | whole-codebase audit for breakages, contract mismatches, duplication, rule violations | claude | ✅ built · 🔒 |
| **feature-verdict** | plan a feature: rules it breaks (memory), code to reuse, options, PRD, tests to stay safe | claude | ✅ built · 🔒 |
| **triage** | correlate a GitHub issue to code (graph+memory), suggest fixes | claude+gh | ✅ built · 🔒 |
| **Data Supply** | feed graph+memory context to a coding agent | — | ✅ *is* `kb-core-ui mcp` (point any MCP client at it) |

AI bots are stdlib-only Python in `bots/`, sharing `bots/common.py` (index →
hand claude the kb-core-ui MCP tools → run prompt → parse output). Graph-only
bots live in `python/kb_core_ui/cli/root.py`. All are in one registry
(`python/kb_core_ui/bots/registry.py`), so
CLI and dashboard list the same set.

> graph-sync earned its keep immediately: on first run it found a real bug
> in kb-core-ui — Go methods spread across a package's files were orphaned
> onto a phantom parent (12 dangling edges). Fixed + regression-tested.

## 3. Memory system — ✅

The counterpart to the graph: the graph answers *where code lives*, memory
answers *what we know that isn't in the code* — primary rules, lessons,
business logic, overviews. Stored as embeddings, searched semantically.

- **Code graph** → SQLite (`python/kb_core_ui/store.py`).
- **Vector memory** → SQLite + embeddings (`python/kb_core_ui/memory`).
  - Default embedder: offline, dependency-free lexical hashing (feature
    hashing + light stemming + cosine, with a calibrated noise floor).
  - Optional neural embedder: set `KB_CORE_UI_EMBED_URL`/`MODEL` (any
    OpenAI-compatible endpoint, e.g. a local Ollama) for true semantic
    recall — no code change, no cloud key required.
- Surfaces: CLI (`kb-core-ui memory add/search/list/rm`), MCP
  (`memory_search`/`memory_add` — bots and agents recall and persist
  knowledge), REST (`/api/memory`), and the web **Memory** tab.

## 4. Control surfaces — ✅

| Surface | Status |
|---|---|
| CLI to run bots + manage memory | ✅ `kb-core-ui bot ...`, `kb-core-ui memory ...` |
| Web graph view | ✅ `kb-core-ui serve` → Graph |
| Web bot dashboard (trigger, live output, run history) | ✅ Bots tab — verified end-to-end |
| Web memory view (search, add, delete) | ✅ Memory tab — verified end-to-end |

## The one thing left for you

Every AI bot is code-complete and stops at the same single wall: the local
`claude` login is expired. Refresh it (`claude` interactively, or export
`ANTHROPIC_API_KEY`), then any AI bot runs for real — e.g.
`kb-core-ui bot pr-review 1 --dry-run`, or the dashboard Run buttons. CI runs
require `ANTHROPIC_API_KEY` as a repo secret (personal logins can't run
unattended).

## Verify everything yourself

```sh
python -m pip install -e "./python[dev]"
cd python && python -m pytest -q && cd ..
cd web && npm run build && cd ..          # frontend, zero TS errors
kb-core-ui bot doctor                       # the orchestration chain
kb-core-ui serve .                          # Graph + Bots + Memory tabs
kb-core-ui memory search "how are call edges resolved"   # semantic recall
kb-core-ui bot graph-sync                   # no-auth bot, runs fully
```

For regression comparison, build the optional oracle from `legacy/go/` with
`go build -o kb-core-ui ./cmd/kb-core-ui` (`kb-core-ui.exe` on Windows), then
run `python -m harness parity --oracle go --candidate python` from `harness/`.
The root `.github/workflows/parity.yml` gates this comparison in CI. Nested
bot workflows remain inactive examples; no paid AI workflow was enabled.

## Possible next steps (not required)

- Consolidate `bots/pr_review.py` onto `bots/common.py` (it predates the
  shared toolkit and duplicates a few helpers).
- Route detection for more frameworks (TS/Next.js, chi/gin) — currently Go
  `net/http`.
- Wire Intercom as a triage data source once it's authorized.
- Persist bot run history (currently in-memory per `serve` process).
