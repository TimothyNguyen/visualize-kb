# kb-core-ui bots

AI bots that operate on this repo (or any repo kb-core-ui has indexed),
using kb-core-ui's MCP server as their source of code context — search the
graph, don't read whole files — instead of a raw file-reading agent loop.

Each bot is a standalone Python script (stdlib only, no `pip install`
needed) that:
1. Shells out to `kb-core-ui parse`/`kb-core-ui mcp` for repo context.
2. Shells out to `claude -p` (headless Claude Code) with a task-specific
   prompt and an MCP config scoped to kb-core-ui's tools.
3. Does something with the result — usually posting to GitHub via `gh`.

## Auth

Bots authenticate however the `claude` CLI on the machine running them is
authenticated:
- **Local/manual runs**: your existing `claude login` session. If it's
  expired, run `claude` interactively once to refresh it.
- **CI (GitHub Actions)**: an interactive login can't work unattended, so
  CI sets `ANTHROPIC_API_KEY` as a repo secret instead — the `claude` CLI
  picks it up automatically over OAuth when present.

`gh` (GitHub CLI) must also be authenticated — locally that's whatever
`gh auth login` you already have; in Actions it's the built-in
`GITHUB_TOKEN`.

## Bots

Before running any bot, verify the chain is connectable:

```sh
kb-core-ui bot doctor
```

This checks python, `gh` (installed + authenticated), `claude` (installed
+ able to actually get a completion), and kb-core-ui's own MCP server (does
it respond with its tools). Every bot also runs these checks itself and
refuses to start with a clear message if a link it needs is broken —
rather than failing deep inside with a raw error.

Some bots are Go-native (pure graph work, no AI/auth needed — they live in
`cmd/kb-core-ui/`); the AI-driven ones are Python scripts here in `bots/`.

| Bot | Impl | Trigger | Needs AI? | Status |
|---|---|---|---|---|
| Doctor (preflight) | `preflight.py` | `kb-core-ui bot doctor` | no | ✅ working |
| Graph Sync | Go | `kb-core-ui bot graph-sync`, or on push via `.github/workflows/graph-sync-bot.yml` | no | ✅ working |
| PR Review | `pr_review.py` | `kb-core-ui bot pr-review <pr>`, or on push via `.github/workflows/pr-review-bot.yml` | yes | ✅ working (needs `claude` auth) |
| Commit Check | `commit_check.py` | `kb-core-ui bot commit-check [ref]` | yes | ✅ working (needs `claude` auth) |
| Test Writer | `test_writer.py` | `kb-core-ui bot test-writer <symbol-or-file>` | yes | ✅ working (needs `claude` auth) |
| Anomaly Detector | `anomaly_scan.py` | `kb-core-ui bot anomaly-scan` | yes | ✅ working (needs `claude` auth) |
| Feature Verdict | `feature_verdict.py` | `kb-core-ui bot feature-verdict "<feature>"` | yes | ✅ working (needs `claude` auth) |
| Support Triage | `triage.py` | `kb-core-ui bot triage <issue#>` | yes | ✅ working — GitHub source (Intercom planned, needs auth) |
| Data Supply | — | `kb-core-ui mcp <path>` | no | ✅ this *is* the MCP server; point any MCP client at it |

The AI bots share `common.py` (index → hand claude the kb-core-ui MCP tools,
which cover both the code graph and the vector memory → run a prompt →
parse output). Add new AI bots by writing a thin script against that
toolkit and registering them in `internal/bots/registry.go`.
| Commit Check | — | — | planned |
| Test Writer | — | — | planned |
| Graph Sync | — | — | planned |
| Anomaly Detector | — | — | planned |
| Data Supply (MCP) | — | — | planned — this is kb-core-ui's existing `kb-core-ui mcp` server, already usable by any MCP client |
| Support Triage (GitHub issues + chat/Intercom) | — | — | planned — Intercom needs to be authorized first |
| Feature Verdict (PRD/impact analysis) | — | — | planned |

### PR Review

Reviews an open PR's diff for: breaking changes (via `get_callers` on
anything touched), code quality, duplication (via `search_symbol` before
flagging), unnecessary rewrites, pattern-consistency with the rest of the
codebase, and cross-boundary contract mismatches (e.g. a frontend assuming
a shape the backend doesn't actually send).

```sh
# from the repo root, with kb-core-ui built (go build -o kb-core-ui ./cmd/kb-core-ui)
kb-core-ui bot pr-review 12          # posts a comment on PR #12
kb-core-ui bot pr-review 12 --dry-run  # prints the review instead of posting
```

Runs automatically on every PR push once `ANTHROPIC_API_KEY` is set as a
repo secret — see `.github/workflows/pr-review-bot.yml`.
