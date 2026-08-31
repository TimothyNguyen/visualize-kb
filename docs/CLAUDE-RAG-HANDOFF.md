# Claude Handoff: Remaining Workspace GraphRAG Work

## Objective

Continue `spec/rag-chatbot-manager-SPEC.md` from T9 through T19 on branch
`rag-chatbot-manager`. Build stateful, workspace-scoped GraphRAG chat and UI
without breaking existing local graph explorer, Go/Python parity, or
`RAG_ENABLE=false` behavior.

Canonical requirements live in `spec/rag-chatbot-manager-SPEC.md`. This file
is execution context, not replacement spec.

## Starting State

- Branch: `rag-chatbot-manager`
- Handoff base commit: `73ea8a332c84988c2bc77bf48b273eaa540aab70`
- Completed: T1-T8 and T20
- Remaining: T9-T19
- Base implementation test result: Python core `128 passed`
- Harness test result: `128 passed`
- Dynamic RAG workflow: all 12 stages pass against fake backend and pinned
  `falkordb/falkordb:v4.20.4`

Relevant commits:

```text
73ea8a3 feat(rag): add workspace management surface
2a7edfa T7: Add hybrid FalkorDB retrieval indexes
44813e7 T6: Add repo and document ingestion
750615d T5: Add idempotent source reconciler
a4810db T20: Add dynamic RAG harness
```

## Non-Negotiable Workflow

For every remaining task:

1. Read task requirements and cited constraints in spec.
2. Change task marker from `.` to `~` before implementation.
3. Add contract/unit tests first and run them red.
4. Implement through existing boundaries rather than parallel abstractions.
5. Add one required dynamic stage to `REQUIRED_STAGES` in
   `kb-core-ui/harness/harness/rag_workflow.py`.
6. Run deterministic fake workflow.
7. If FalkorDB behavior changed, run same workflow against pinned
   `falkordb/falkordb:v4.20.4`.
8. Run affected suites plus full Python, harness, and web regressions.
9. Change task marker to `x` only after composed workflow passes with no
   skipped required stage.
10. Commit task separately. Do not combine all remaining tasks into one
    commit. Do not push unless explicitly requested.

Preserve these invariants:

- Browser never connects to FalkorDB or provider APIs directly.
- Every read and write is workspace-scoped server-side.
- User values never become raw graph names, labels, relationships, property
  names, or Cypher fragments.
- Existing Graph, Bots, Memory, REST, MCP, SQLite, and static `graph.json`
  paths continue working with GraphRAG disabled.
- Secrets stay server-only and never enter API health payloads, frontend
  bundles, logs, reports, citations, or persisted checkpoints.
- FalkorDB reference projects inform design only. Do not copy their APIs and
  do not add either GitHub repository as runtime dependency.

## Existing Architecture

### Domain and Persistence

- `kb-core-ui/python/kb_core_ui/rag/contracts.py`: normalized graph envelope,
  stable IDs, citations, chunks, nodes, relationships.
- `kb-core-ui/python/kb_core_ui/rag/workspaces.py`: persistent workspace,
  source, and ingestion-run lifecycle.
- `kb-core-ui/python/kb_core_ui/rag/normalizer.py`: validation, bounds,
  dangling-edge rejection.
- `kb-core-ui/python/kb_core_ui/rag/falkordb_adapter.py`: connection, graph
  lifecycle, source-scoped writes/deletes, retries, timeouts, read-only query
  entry point.
- `kb-core-ui/python/kb_core_ui/rag/reconciler.py`: idempotent staged publish,
  rollback, retry convergence, stale source cleanup.
- `kb-core-ui/python/kb_core_ui/rag/ingestion.py`: repo JSON and document-set
  ingestion into common envelope.
- `kb-core-ui/python/kb_core_ui/rag/indexing.py`: `FalkorDBGraph` document load,
  retrieval indexes, embeddings, full-text/vector hybrid retrieval.
- `kb-core-ui/python/kb_core_ui/rag/manager.py`: shared CLI/HTTP management
  boundary for workspace/source/run lifecycle, health, stats, and bounded
  graph context.

### Server and CLI

- `kb-core-ui/python/kb_core_ui/server/app.py`: in-process REST router and
  handlers. Current RAG routes are under `/api/rag/workspaces`.
- `kb-core-ui/python/kb_core_ui/server/httpd.py`: socket transport.
- `kb-core-ui/python/kb_core_ui/cli/root.py`: workspace commands.
- `kb-core-ui/python/kb_core_ui/cli/command.py`: custom Cobra-compatible
  command framework.

Current CLI operations:

```text
workspace list
workspace create <id> --name <name>
workspace delete <id>
workspace source add <workspace> <source> --kind <kind> --uri <uri> [--ref <ref>]
workspace source remove <workspace> <source>
workspace source refresh <workspace> <source>
workspace ingestion start <workspace> <source>
workspace ingestion cancel <workspace> <run>
workspace run <workspace> <run>
workspace health <workspace>
workspace stats <workspace>
workspace context <workspace> [--source <source>] [--limit <n>]
```

`workspace` is intentionally hidden from root help because archived Go CLI
help is a byte-for-byte parity contract. Command remains directly invokable
and `kb-core-ui workspace --help` works. Do not expose it in root help unless
the parity contract and oracle strategy are deliberately changed.

### Harness

- `kb-core-ui/harness/harness/rag_workflow.py`: required composed stages.
- `kb-core-ui/harness/harness/rag_fakes.py`: semantic in-memory FalkorDB fake.
- `kb-core-ui/harness/tests/test_rag_workflow.py`: required-stage/report gate.
- `.github/workflows/rag-harness.yml`: fake and pinned-service CI jobs.

Add fake support narrowly. Fake query branches must model only fixed queries
owned by production code, never become a permissive Cypher interpreter.

## Known Gaps

These are current behavior, not completed future requirements:

- `start_ingestion` and `refresh_source` create queued runs; no background
  coordinator consumes them yet. Add explicit execution/cancellation ownership
  before ingestion UI depends on these endpoints. Do not report queued as
  running or succeeded.
- Current `validate_read_only_cypher` rejects writes, `CALL`, multiple
  statements, and missing `$workspace_id`, but does not yet implement T9's
  complete schema allowlist for labels, relationships, properties, parameters,
  result limits, and generated-query parsing.
- Current bounded context response returns knowledge-node records. T9/T11 may
  extend this into a citation-safe subgraph response while preserving hard row
  limits and workspace/source scope.
- No LangGraph workflow, provider abstraction, chat persistence, SSE chat API,
  chat UI, auth policy, observability layer, or production Compose stack exists.
- `@falkordb/ui-chat`, LangGraph, and provider SDK dependencies are not yet in
  package manifests. Keep them in optional RAG/UI paths and verify compatible
  versions before pinning.

## Remaining Tasks

### T9: LangGraph RAG Workflow

Build backend workflow before HTTP streaming or UI.

Deliver:

- Typed workflow state containing workspace, allowed source IDs, query,
  strategy, retrieval evidence, graph evidence, citations, answer, degraded
  state, errors, timing, and cancellation signal.
- Nodes for scope validation, hybrid retrieval, entity/chunk expansion,
  optional safe graph query, evidence ranking/deduplication, answer synthesis,
  and citation validation.
- Deterministic routing for empty retrieval, transient FalkorDB failure,
  graph-query rejection, vector-only degraded fallback, provider retry, and
  insufficient evidence.
- Provider protocols plus deterministic fake chat model. Default tests and CI
  must not need external API keys.
- Hard retrieval/traversal/result/token limits from request plus server config.
- Strong Cypher validator: parser/token validation against allowlisted clauses,
  labels, relationship types, properties, parameters, required workspace
  predicate, timeout, and row limit. Never patch unsafe generated Cypher and
  execute it; reject and take safe fallback branch.
- Citation grounding check: every answer citation resolves to retrieved source
  metadata; unsupported claims produce explicit insufficient-evidence answer.

Reuse `HybridRetriever` and `FalkorDBAdapter.read_query`. Do not create another
database client inside workflow nodes.

Harness stage should prove at least:

- cross-source question returns evidence from allowed sources only;
- another workspace/source ID supplied by caller cannot escape scope;
- empty query path returns insufficient evidence;
- rejected generated Cypher never reaches adapter;
- graph failure returns marked degraded answer when vector evidence exists;
- answer citations all map to returned evidence.

### T10: Workspace-Scoped Chat Persistence

Deliver:

- Thread identity bound to workspace, not caller-provided global ID alone.
- FalkorDB-backed checkpoint/history adapter or compatible saver abstraction.
- Atomic persistence of complete turns only; partial streamed answer is never
  persisted as complete.
- Restart-safe replay, retention policy, thread deletion, workspace cleanup,
  and source/workspace isolation.
- Provider secrets and raw credentials excluded from state snapshots.
- Fake persistence adapter for deterministic tests.

Harness stage should write, reopen, resume, isolate two workspaces, expire or
delete a thread, and prove cleanup does not affect another workspace.

### T11: REST and SSE Chat Contract

Freeze typed backend/frontend contract before UI integration.

Deliver:

- Endpoints for complete chat, SSE stream, cancellation/disconnect,
  suggestions, feedback, context, source map, graph explanation, and thread
  retrieval/cleanup.
- Versioned JSON/SSE fixtures covering `answer`, `query_id`, `workspace_id`,
  `context`, `explain_graph`, `source_map`, `strategy`, `degraded`, and `error`.
- Explicit event names and terminal semantics. Send one terminal completion or
  error event. Heartbeats must not be interpreted as content.
- Disconnect propagation into retrieval/provider work and resource cleanup.
- Stable 400/404/409/413/429/503 mappings without secret-bearing error text.
- Add corresponding TypeScript types and client methods.

Use current `Server`/`Mux` conventions and preserve all existing route bodies.
Harness must exercise real HTTP transport, not only call workflow methods.

### T12: Chat UI

Integrate `@falkordb/ui-chat` as presentation only.

Deliver:

- Add compatible package version and custom-element typings.
- `/chat` route and navigation entry without disturbing existing routes.
- Workspace selector and strategies: `auto`, `local`, `multi_path`.
- SSE accumulation, abort, retry, suggestions, feedback, citations, sources,
  graph explanation, source map, loading, empty, degraded, and error states.
- Citation/entity/source click navigation through existing React router and
  graph/file views.
- Responsive desktop/mobile layout matching existing visual language.

Never place FalkorDB URL, credentials, or provider keys in Vite environment.
Frontend talks only to backend contract from T11.

Harness/browser stage should cover stream rendering, abort, workspace switch,
strategy selection, citation navigation, unavailable source target, degraded
response, and retained existing routes.

### T13: Ingestion UI and Execution Coordinator

Deliver:

- Backend coordinator that owns queued -> running -> terminal transitions and
  cancellation. Make retries and refresh execution explicit.
- Source form for local/GitHub repo, branch/commit, document upload/set, and URL.
- Upload/body/file count/size limits and server-side staging cleanup.
- Run progress, failure details, rejection report, refresh/delete controls, and
  workspace graph stats.
- Polling or events must stop on terminal state and component unmount.

Harness stage should submit each supported source shape through real API,
observe state transitions, cancel one run, retry one failure, and verify source
isolation after refresh/delete.

### T14: Existing Graph Explorer Compatibility

Deliver:

- Selected workspace can open graph overview and bounded subgraph.
- Citation can focus existing symbol/file view when mapping exists.
- Missing mapping shows recoverable UI state.
- Static `graph.json` and existing SQLite-backed views still work with
  `RAG_ENABLE=false` and no FalkorDB process.

Harness must explicitly run legacy Graph/Bots/Memory routes and web tests in
disabled mode, plus workspace graph navigation in enabled mode.

### T15: Auth and Tenant Boundary

Deliver before claiming shared deployment readiness:

- Injectable workspace authorization/tenant policy at every workspace route,
  workflow start, thread operation, source operation, and graph read.
- Default local policy preserving current local developer experience.
- Strict CORS/origin policy option, rate limiting, request/upload limits,
  provider-secret redaction, audit events, and safe errors.
- Authorization happens before adapter selection or resource existence leaks.

Harness stage must prove denied caller cannot distinguish/read/mutate another
workspace and no denied request reaches FalkorDB/provider fakes.

### T16: Consolidated Verification Matrix

Fill remaining test matrix from spec V1-V14:

- normalizer goldens and deterministic IDs;
- duplicate/retry/delete reconciliation;
- cross-source/cross-repo retrieval and workspace isolation;
- complete Cypher validator matrix;
- empty/degraded workflow;
- persistence isolation;
- SSE cancellation and partial-turn behavior;
- React chat/ingestion/navigation behavior;
- existing regression suites with RAG disabled.

Do not duplicate tests already proving these behaviors. T16 closes measurable
coverage gaps discovered by matrix review.

### T17: Pinned Development Stack

Deliver:

- Docker Compose with exact FalkorDB version, health check, persistent volume,
  seeded fixture workspace, deterministic fake LLM/embeddings, and reset path.
- Optional real-provider profile driven by server-only environment variables.
- Startup, migration, seed, reset, and teardown docs.
- Keep CI image synchronized with Compose pin.

Harness stage starts clean stack, seeds, chats, restarts, verifies persistence,
resets, and verifies clean state.

### T18: Observability and Performance Gates

Deliver:

- Structured metrics for ingestion states/counts/rejections/embedding failures,
  retrieval latency, graph latency, provider latency, token usage, first token,
  completion, cancellation, degraded responses, and memory growth.
- No source content, prompts, answers, credentials, or provider secrets in
  metrics/logs by default.
- Fixture budgets and baseline report for ingestion, retrieval, first token,
  complete answer, memory growth, and concurrent workspace isolation.
- Deterministic thresholds with enough tolerance for CI variance.

### T19: Security and Operations Documentation

Deliver final operational docs:

- threat model and trust boundaries;
- data flow and data classification;
- provider retention assumptions;
- prompt-injection and untrusted-source handling;
- extracted/inferred/ambiguous/source-trust labels;
- backup/restore, graph reset, schema/index upgrade, rollback, credential
  rotation, incident response, and deletion semantics.

Validate commands in docs through harness or smoke scripts. Documentation-only
claims do not satisfy V16 unless their procedures execute successfully.

## Recommended Execution Order

Follow spec dependency order:

```text
T9 -> T10 -> T11
T12 -> T13 -> T14
T15 -> T16
T17 -> T18 -> T19
```

Do not start frontend integration before T11 response/event fixtures are frozen.
Do not claim shared deployment before T15. Do not tune performance before T16
behavioral matrix is stable.

## Verification Commands

Python core:

```powershell
cd kb-core-ui/python
python -m pytest -q
```

Harness suite with RAG dependencies available in repository environment:

```powershell
cd kb-core-ui/harness
..\..\.venv-ui\Scripts\python.exe -m pytest -q
..\..\.venv-ui\Scripts\python.exe -m harness rag --backend fake --report .harness-work/rag/fake.json
```

Pinned FalkorDB without disturbing any service already using port 6379:

```powershell
docker run -d --rm --name visualize-kb-rag-falkordb `
  -p 127.0.0.1:6380:6379 `
  --health-cmd "redis-cli ping" `
  --health-interval 5s --health-timeout 3s --health-retries 20 `
  falkordb/falkordb:v4.20.4

$env:RAG_ENABLE = "true"
$env:FALKORDB_URL = "falkor://127.0.0.1:6380"
$env:RAG_LLM_PROVIDER = "harness-fake"
$env:RAG_LLM_MODEL = "harness-fake"
$env:RAG_EMBEDDING_MODEL = "harness-fake"
..\..\.venv-ui\Scripts\python.exe -m harness rag `
  --backend falkordb --report .harness-work/rag/falkordb.json

docker stop visualize-kb-rag-falkordb
```

Web:

```powershell
cd kb-core-ui/web
pnpm test
pnpm lint
pnpm build
```

Before each commit:

```powershell
git diff --check
git status --short
```

## First Action

Start T9 only. Read current retrieval and adapter tests, write failing workflow
contracts, add `langgraph_rag` required harness stage, then implement smallest
safe workflow that passes fake and pinned FalkorDB composition. Do not begin T10
until T9 is committed and worktree is clean.
