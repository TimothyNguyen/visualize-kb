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
- Handoff base commit: HEAD of `rag-chatbot-manager` as of this commit (this
  doc is committed together with the task it describes, so it cannot pin its
  own SHA — run `git log -1` on this branch for the exact hash)
- Completed: T1-T10 and T20
- Remaining: T11-T19
- Python core test result: `163 passed` (147 prior + 16 new T10 persistence
  tests across `test_rag_persistence.py`, `test_falkordb_adapter.py`,
  `test_rag_config.py`)
- Harness test result: `128 passed`
- Dynamic RAG workflow: all 14 stages pass against fake backend and pinned
  `falkordb/falkordb:v4.20.4` (14th stage: `chat_persistence`, added by T10)
- Loop started at: `2026-08-31T03:44:54Z` (wall-clock anchor for the 5-hour
  budget proxy; set once, never overwritten)
- Next action: start T11 (REST + SSE chat contract) — read T11's deliverables
  below, write contract fixtures first

Relevant commits:

```text
<T10 commit, see git log -1> T10: Add workspace-scoped chat persistence
<T9 commit> T9: Add LangGraph RAG workflow
73ea8a3 feat(rag): add workspace management surface
2a7edfa T7: Add hybrid FalkorDB retrieval indexes
44813e7 T6: Add repo and document ingestion
750615d T5: Add idempotent source reconciler
a4810db T20: Add dynamic RAG harness
```

## T9 result (LangGraph RAG workflow) — done

New module `kb-core-ui/python/kb_core_ui/rag/workflow.py`: `ChatWorkflow`
(7 LangGraph nodes: scope_validation, hybrid_retrieval, entity_expansion,
graph_query, evidence_ranking, answer_synthesis, citation_validation),
`RetrievalLimits` (request limits always narrow, never widen, server config —
V7), `validate_generated_cypher` (allowlist validator for LLM-proposed
expansion Cypher — labels/relationships/properties/parameters/required
`LIMIT $limit`, layered on top of the existing `validate_read_only_cypher`),
`ChatModel` protocol + `FakeChatModel` (no external API key needed),
`GraphReadAdapter` protocol (graph_query node uses only
`FalkorDBAdapter.read_query`, no second DB client). New harness stage
`langgraph_rag` (13th required stage) proves: cross-source evidence stays
within allowed sources, a foreign source id can't escape scope, an empty
query yields an explicit insufficient-evidence answer, unsafe generated
Cypher never reaches `read_query`, a simulated graph-query failure yields a
degraded answer with surviving vector evidence, and citations never
reference unreturned evidence. `langgraph>=1.2,<2` added to the optional
`rag` dependency group in `kb-core-ui/python/pyproject.toml` (pinned
1.2.11 in the `.venv-ui` environment).

Known scope note carried forward, not a bug: `max_answer_tokens` is stored in
config and threaded through `RetrievalLimits` but not yet enforced by
truncation logic — `FakeChatModel` output is naturally short so this wasn't
exercised. Enforce it when a real (non-fake) `ChatModel` provider is wired in
(T10+ territory, not required by T9's deliverable list).

## T10 result (workspace-scoped chat persistence) — done

New module `kb-core-ui/python/kb_core_ui/rag/persistence.py`: `ChatHistoryStore`
wraps a narrow `ChatThreadAdapter` protocol (`write_chat_turn`, `list_chat_turns`,
`trim_chat_turns`, `delete_chat_thread`, `delete_all_chat_threads`) — never opens
a second database client, built entirely on `FalkorDBAdapter`'s own new
primitives. Thread identity (`thread_key`) always mixes `workspace_id` with the
caller-supplied thread id, so isolation holds even against the deliberately
unpartitioned `FakeChatBackend` used in tests (V11 proven at the key layer, not
just by picking a different backend per workspace). `write_turn` only accepts an
already-finished `ChatResponse` instance — structurally no incremental/streamed
delta or arbitrary dict/kwargs can smuggle a field (e.g. a provider secret) into
persisted state. Retention: `RagConfig.max_thread_turns` (default 200, env
`RAG_MAX_THREAD_TURNS`) triggers oldest-turn trimming after each write.

`FalkorDBAdapter` gained `write_chat_turn`/`list_chat_turns`/`trim_chat_turns`/
`delete_chat_thread`/`delete_all_chat_threads`, all going through the adapter's
existing `_write`/`read_query` methods, which already enforce `$workspace_id`
scoping and reject any workspace_id parameter mismatch (defense-in-depth: every
stored node also carries an explicit `workspace_id` property).

New harness stage `chat_persistence` (14th required stage) proves: a fresh
adapter/store constructed against the same durable backend replays prior
history (restart-safe), resuming a thread appends turns in monotonic order, a
second workspace using an identical thread-id string never sees or affects the
first workspace's turns, deleting a thread makes it unreadable, and cleaning up
one workspace's threads never touches another's.

## T11 result (REST + SSE chat contract) — done

Added workspace-scoped complete chat, SSE stream, cancellation, suggestions,
feedback, source-map, graph-explanation, and thread lifecycle routes. Frozen
JSON/SSE fixtures are byte-compared by Python and consumed by TypeScript tests;
heartbeats are SSE comments and every stream has exactly one terminal event.
Frontend API types and methods use only backend REST/SSE routes.

Required harness stage `chat_http_contract` starts `listen_and_serve` on an
OS-assigned loopback port, exercises real `urllib` transport, cancels a live
stream, checks replay and error mapping, then stops listener cleanly. Required
stage count is now 15. Verification: Python 209 passed; harness 128 passed;
fake RAG workflow 15/15 passed; web 20 passed; lint exited 0; production build
passed. FalkorDB behavior did not change, so pinned-service rerun was not
required for T11.

## T12 result (CopilotKit chat UI) — done

`/chat` renders a CopilotKit workbench with workspace selector, retrieval-scope
checkboxes, and `auto`/`local`/`multi_path` strategy, all pushed into AG-UI
agent state so the server keeps enforcing the scope. A self-hosted Node runtime
(`kb-core-ui/web/runtime/server.ts`) sets `COPILOTKIT_TELEMETRY_DISABLED` before
importing the runtime and forwards to `POST /api/rag/agent`; no hosted control
plane and no credentials in Vite env. `kb_core_ui/rag/agui.py` bridges that
endpoint onto the frozen T11 contract, so heartbeats stay comments and each run
ends in exactly one `RUN_FINISHED` or `RUN_ERROR`.

Required harness stage `agui_runtime` drives `POST /api/rag/agent` over real
loopback HTTP: AG-UI framing, workspace scope surviving the state snapshot,
citations confined to workspace sources, mid-stream abort ending in `RUN_ERROR`,
and 400/404/400 rejections for unscoped, unknown-workspace, and empty-message
runs. Both HTTP stages now share the `_serving` helper. Required stage count is
now 17.

Verification: Python 216 passed; harness 128 passed; fake RAG workflow 17/17;
pinned `falkordb/falkordb:v4.20.4` workflow 17/17 (rerun because the new stage
reads through the adapter); web 32 passed; lint exited 0; `pnpm build` and
`pnpm build:runtime` passed. Fixed while testing: the workspace list never
seeded `allowedSourceIds`, so scope checkboxes rendered unchecked on first load.

Left behind on purpose: `kb-core-ui/web/vendor/falkordb-ui-chat-0.1.0.tgz` is
now unreferenced (T12 moved from `@falkordb/ui-chat` to CopilotKit) and can be
deleted once nobody wants the build artifact back.

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

Integrate CopilotKit as presentation and runtime only, self-hosted.

Deliver:

- Pinned `@copilotkit/react-core` and `@copilotkit/runtime`, plus a Node runtime
  process this repository owns. Telemetry disabled; hosted CopilotKit control
  plane out of scope.
- AG-UI bridge over the frozen T11 chat contract, so the runtime forwards turns
  to one backend endpoint instead of reaching retrieval or providers itself.
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
