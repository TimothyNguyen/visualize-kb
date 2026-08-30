# Company Readiness & Cluster Graphs

## §G

G1. Take `kb-core-ui` from local dev tool → company-grade: safe on a network, tested, installable in 1 command, observable.

G2. Close multi-repo gap by backporting graphify's cluster-graph feature (PR #2134) into `kb-core`.

Maturity today:

|deployment target|rating|
|---|---|
|local developer tool|7/10|
|internal single-user product|5/10|
|shared internal service|3/10|
|customer-facing SaaS|2/10|

## §C

C1. Local-first default stays default. No mandatory cloud/DB dependency.

C2. Architecture stays `UI → Python API → GraphStore (JSON/SQLite default \| FalkorDB optional)`.

C3. FalkorDB ⊥ adopted before SQLite/API traversal proven insufficient by benchmark (V3).

C4. Cluster-graph backport (T15) additive only — existing single-repo `graph.json` schema ⊥ break.

## §I

I.rest. `kb-core-ui/python/kb_core_ui/server/app.py` — REST routes, CORS.

I.httpd. `kb-core-ui/python/kb_core_ui/server/httpd.py` — socket/threading layer.

I.bots. `kb-core-ui/python/kb_core_ui/bots/runner.py` — subprocess execution.

I.store. `kb-core-ui/python/kb_core_ui/store.py` — SQLite schema/migrations.

I.client. `kb-core-ui/web/src/api/client.ts` — graph fetch.

I.ci. `.github/workflows/parity.yml` — only active CI gate.

I.pkg. `kb-core-ui/python/pyproject.toml`, `kb-core-ui/web/package.json`, root `README.md`.

I.cluster. `kb_core/cluster_graph.py`, `kb_core/cluster_cli.py`, `kb_core/cluster_ref.py` (new — ported from graphify), `kb_core/multigraph_compat.py` (existing, inactive), `kb_core/cross_repo_types.py` + `kb_core/global_graph.py` (existing, partial).

## §V

V1. Shared/customer deploy ⊥ ship before authn+authz done (T2).

V2. `--host 0.0.0.0` ⊥ safe without auth. Loopback-only default mitigates today; `_with_cors` in `server/app.py:440` sets `Access-Control-Allow-Origin: *` unconditionally.

V3. FalkorDB adoption ⊥ before incremental-load perf budgets (10k/50k/100k nodes) measured against SQLite baseline (T10 before T11).

V4. Cluster-graph backport preserves existing single-repo graph schema; composition is additive namespaced merge, not a schema rewrite.

V5. `kb-core-ui/python/kb_core_ui/server/httpd.py:37-38` reads `Content-Length` unbounded and has no request timeout; `log_message` (line 31-33) is a no-op — no access logs today.

V6. Enterprise controls (T14) ⊥ built before deployment model (T1) chooses shared/SaaS — no SSO/tenancy work while local-single-user is the target.

## §T

|id|status|task|cites|
|---|---|---|---|
|T1|.|Declare deployment model: local single-user \| shared internal service \| customer SaaS. Decision only, no code.|G1|
|T2|.|Secure API before network exposure: authn+sessions/API tokens, RBAC (read/memory-write/bot-run/admin), CORS origin allowlist + CSRF, request/body limits, rate limits, bot concurrency quotas, bot timeout/cancel/output limits, secret redaction, audit trail, TLS or documented reverse-proxy.|V1,V2,I.rest,I.bots|
|T3|.|Real CI gate: full kb-core test suite, frontend test/lint/build, ruff/pyright/bandit/pip-audit, npm audit, Windows/macOS matrix, package-install smoke tests, REST/browser e2e, coverage thresholds.|I.ci|
|T4|.|Fix frontend test runner — `npm test` currently fails before running: "Timeout waiting for worker to respond", 0 test files collected. Lint and prod build both pass.|I.client|
|T5|.|One-command install: supported installer/packaged launcher, Dockerfile/Compose, Windows/macOS/Linux smoke-tested commands, version + dependency-error checks, upgrade/uninstall docs, stable config reference.|I.pkg|
|T6|.|HTTP server hardening: cap `Content-Length`, add request timeout, add access logs.|V5,I.httpd|
|T7|.|Bot execution reliability: persistent job queue/history (survives restart), bounded worker pool, cancellation/timeout/retry policy, graceful termination.|I.bots|
|T8|.|Add `/healthz` + `/readyz`, graceful shutdown.|I.rest|
|T9|.|Versioned DB migrations (replace ad hoc logic at `store.py:137`), backup/restore, corruption recovery, migration rollback — all tested.|I.store|
|T10|.|Incremental graph loading: initial community overview, incremental subgraph endpoint, pagination/server-side filtering, cancel stale requests, Web Worker parsing/layout, render limits/viewport culling, perf budgets @ 10k/50k/100k nodes, automated load benchmarks in CI. Current graph ≈13,000 nodes; `client.ts` still loads the full static `graph.json`.|V3,I.client|
|T11|.|Evaluate FalkorDB against measured SQLite baseline. Blocked on T10 numbers — FalkorDB doesn't help if the browser still receives/renders the full graph.|V3,T10|
|T12|.|Observability: structured request/job logs, correlation IDs, metrics (index duration, graph size, API latency, failures), audit log (source access, memory edits, bot exec), crash-reporting policy, retention/rotation, deployment runbook, upgrade/rollback procedure, resource limits, support diagnostics bundle.||
|T13|.|Packaging + governance: `pyproject.toml` `license`/`readme`/`urls`/`classifiers` (currently absent), frontend version off `0.0.0`, root `LICENSE` + `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, release notes, compatibility/support policy, dependency automation, explicit policy for source code sent to Claude/GitHub/embedding providers.|I.pkg|
|T14|.|Enterprise controls (only if T1 picks shared/SaaS): SSO/OIDC, org/project isolation, tenant-scoped storage, fine-grained repo permissions, immutable audit logs, encryption/key management, private-network deploy, data deletion/export, retention controls, HA/DR, compliance docs + dependency SBOM.|V6,T1|
|T15|x|Backport graphify cluster-graph feature into kb-core: `cluster_graph.py` (spec/composition/selectors/links), `cluster_cli.py` (`cluster init/add/check/build/remove`), `cluster_ref.py` (member-marker lifecycle), wire `--cluster` flag into `query`/`path`/`explain`/`affected`, activate `multigraph_compat.py` call sites. Fixes kb-core-ui's single-repo-per-run limit.|C4,V4,I.cluster|

## §B

|id|date|cause|fix|
|---|---|---|---|

Recommended order: T1 → T4+T3 → T2 → T5 → T10 → T9 → T12 → T11 → T14 (only if T1 picks shared/SaaS). T15 runs parallel-track — feature addition, not a hardening blocker.
