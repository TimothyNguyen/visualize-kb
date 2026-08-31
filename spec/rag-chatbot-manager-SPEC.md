# Workspace GraphRAG Chatbot Manager

## §G

G1. Hackathon MVP: turn internal KB Core graph JSON plus document corpora into workspace-scoped FalkorDB knowledge graphs, then answer repo, docs, and cross-repo questions in existing React UI through a CopilotKit-backed GraphRAG chatbot.

G2. Internal-use only. Keep current local graph explorer working without FalkorDB. GraphRAG is opt-in backend capability; no browser talks to FalkorDB or model providers directly.

Hackathon boundary: optimize for one trusted internal team, local/private infrastructure, deterministic demo data, and working repo/document questions. Public SaaS, external tenants, hosted CopilotKit/FalkorDB control planes, enterprise compliance evidence, and production SLOs are post-hackathon.

## §C

C1. Sources: local internal repo, uploaded internal document set, or many internal sources combined in one workspace. GitHub URL, branch/commit fetch, and document URL are post-hackathon.

C2. Repo source starts from KB Core `graph.json`; document source uses GraphRAG-SDK-compatible extraction into the same normalized graph envelope.

C3. One FalkorDB graph per workspace. Every node, edge, chunk, citation, and chat checkpoint also carries `workspace_id` and `source_id` defense-in-depth metadata.

C4. Ingestion idempotent by source content hash + extractor/schema version. Re-run unchanged source = no duplicate graph facts or embeddings.

C5. Source refresh removes stale facts/chunks owned by that source only. It never deletes facts owned by another source in same workspace.

C6. FalkorDB graph names derive from validated workspace IDs. User input never becomes raw Cypher, graph name, label, or relationship type without validation.

C7. Retrieval combines lexical/vector candidate search with bounded graph traversal. Vector-only fallback allowed only when graph retrieval unavailable; response marks degraded mode.

C8. Generated Cypher is read-only, parameterized, schema-constrained, timeout-bounded, and executed with read-only credentials. No chat path can mutate FalkorDB.

C9. Chat answer includes source citations and retrieval metadata. Unsupported claim -> explicit insufficient-evidence response.

C10. Existing `graph.json`, graph REST/MCP routes, SQLite stores, and current Graph/Bots/Memory UI flows remain backward compatible.

C11. CopilotKit is presentation/runtime integration only. Backend owns workspace scope, retrieval, authorization boundary, citations, persistence, and stream protocol. CopilotKit telemetry is disabled; hosted CopilotKit control plane is out of scope.

C12. Local Docker or approved internal FalkorDB use same adapter/config contract. Missing FalkorDB or approved model config fails RAG health checks clearly; base graph UI still starts.

## §I

I.graph_json. `kb-core-out/graph.json` and `kb-core-ui/web/public/kb-core-out/graph.json` — current graph export and browser fixture.

I.extract. `kb-core` extraction pipeline — repo AST/relationship source; must remain source of truth for code graph facts.

I.server. `kb-core-ui/python/kb_core_ui/server/app.py` and `httpd.py` — additive workspace, ingestion, RAG, and SSE routes.

I.cli. `kb-core-ui/python/kb_core_ui/cli/root.py` — additive `workspace`/`rag` commands and FalkorDB config wiring.

I.pkg. `kb-core-ui/python/kb_core_ui/pyproject.toml` — optional RAG dependency group; default install remains local-first.

I.client. `kb-core-ui/web/src/api/client.ts` and `types.ts` — typed workspace, ingestion, chat, stream, citation, and graph-context API.

I.routes. `kb-core-ui/web/src/main.tsx`, `App.tsx`, `Header`, and new `ChatView` — workspace selector + chatbot route.

I.falkor. `https://github.com/fatemenajafi135/GraphRAG` — reference service shape: ontology/source upload, KG create/extend, FastAPI chat. Adapt patterns; do not copy its API or make it a runtime dependency.

I.falkor_blog. `https://www.falkordb.com/blog/graphrag-langchain-langgrap/` — reference integration: `langchain-falkordb`, `FalkorDBGraph`, `FalkorDBVector` hybrid search, LangGraph routing/checkpoints, read-only Cypher safeguards.

I.copilotkit. `https://docs.copilotkit.ai/` — approved internal frontend/runtime candidate: React chat, AG-UI streaming, self-hosted runtime, agent tools, threads, and state.

I.config. `FALKORDB_URL`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `FALKORDB_SSL`, `RAG_LLM_PROVIDER`, `RAG_LLM_MODEL`, `RAG_EMBEDDING_MODEL`, `RAG_MAX_CONTEXT`, `RAG_ENABLE`, and `COPILOTKIT_TELEMETRY_DISABLED` — server-only configuration; secrets never enter frontend bundle.

I.harness. `kb-core-ui/harness/harness/rag_workflow.py`, `python -m harness rag`, and `.github/workflows/rag-harness.yml` — dynamic composition gate; fake backend always, pinned FalkorDB service when DB behavior changes.

## §V

V1. Normalizer accepts current NetworkX `nodes` + `links` and legacy `edges`; output uses one versioned envelope with stable IDs, source ownership, node/edge type, text, and source location.

V2. Normalized node ID is deterministic from `workspace_id`, `source_id`, source-relative identity, and extractor version. Same input produces same IDs across runs and machines.

V3. Every persisted graph fact is traceable to source ID + source location or chunk ID. Inferred facts are marked `INFERRED`; extracted facts are marked `EXTRACTED`; uncertain facts are marked `AMBIGUOUS`.

V4. Ingestion validates schema, rejects dangling edges, bounds field sizes, records rejected records, and publishes new source version only after all writes and index checks pass.

V5. Reconcile is source-transactional: retry after interruption converges to target source version; stale source-owned nodes, edges, chunks, and embeddings are removed; unrelated source data survives.

V6. Workspace query cannot read another workspace, even when caller supplies another graph ID, source ID, node ID, or citation ID.

V7. Chat retrieval executes bounded hybrid search, then bounded graph expansion from retrieved entities/chunks. Limits are explicit in request and server config; no unbounded traversal.

V8. LLM output never becomes executable Cypher without parser validation against allowlisted read-only clauses, labels, relationships, properties, parameters, timeout, and result row limit.

V9. Chat response schema supports complete and streamed responses: `answer`, `query_id`, `workspace_id`, `context`, `explain_graph`, `source_map`, `strategy`, `degraded`, and `error`.

V10. Stream disconnect cancels retrieval/LLM work when provider supports cancellation; server closes worker resources and does not persist partial assistant answer as complete.

V11. Conversation thread ID is workspace-scoped. Restart-safe history/checkpoints use FalkorDB-backed persistence when enabled; no cross-workspace history leakage.

V12. UI renders source citation click -> source/file/graph context. Missing source target shows a recoverable message, never a dead link or crash.

V13. Current Graph/Bots/Memory routes and tests pass with `RAG_ENABLE=false` and no FalkorDB connection.

V14. RAG contract tests pass against fake adapter; integration tests pass against pinned local FalkorDB Docker image and mocked LLM/embeddings. External provider tests are opt-in and never required for default CI.

V15. Metrics expose ingestion run state, files/chunks/nodes/edges, rejected records, embedding failures, retrieval latency, graph query latency, LLM latency, token usage, stream cancellation, and degraded responses without logging secrets or source content by default.

V16. No task becomes `x` from isolated unit tests alone. Each task adds/updates a dynamic harness stage that composes its real boundaries. Default CI runs deterministic fake LLM/embedding/provider dependencies; FalkorDB-touching tasks also pass against pinned FalkorDB service. Harness emits machine-readable stage report and fails on skipped required stage.

## §T

|id|status|task|cites|
|---|---|---|---|
|T1|x|Freeze versioned normalized graph envelope and mapping from current KB Core `graph.json` (`links`/`edges`) to FalkorDB nodes, relationships, chunks, citations, and provenance.|V1,V2,V3,I.graph_json,I.extract|
|T2|x|Define workspace/source/run persistence model, IDs, lifecycle, graph-name derivation, source ownership, status states, and config validation. Keep local default path unchanged.|C1,C3,C6,C12,V6,I.config|
|T3|x|Add JSON normalizer + validator: schema version, deterministic IDs, source metadata, edge endpoint checks, size limits, rejection report, and golden fixtures for repo/docs/cross-repo inputs.|V1,V2,V3,V4|
|T4|x|Build FalkorDB adapter with connection health, graph lifecycle, parameterized upsert/delete, read-only query mode, retries, timeouts, and local/Cloud configuration.|C3,C6,C8,C12,V4,V6,I.config|
|T5|x|Implement idempotent source reconciler: manifest/hash check, transactional staging, source-owned stale deletion, retry convergence, publish marker, and rollback/recovery handling.|C4,C5,V4,V5,V16,I.harness|
|T6|x|Implement repo ingestion from KB Core JSON and document ingestion using GraphRAG-SDK-compatible loaders/chunking/entity-relation extraction. Emit same normalized envelope for both.|C1,C2,V1,V3,V16,I.extract,I.falkor,I.harness|
|T7|x|Load `GraphDocument`-equivalent facts through `FalkorDBGraph`; create versioned full-text/vector indexes; embed chunk text and selected graph properties through `FalkorDBVector` hybrid search.|C2,C7,V3,V7,V16,I.falkor_blog,I.harness|
|T8|x|Add workspace CLI/API: list/create/delete workspace, add/remove/refresh sources, start/cancel ingestion, run status, health, stats, and bounded graph/subgraph context.|C1,C3,C5,V4,V6,V16,I.server,I.cli,I.harness|
|T9|x|Build LangGraph RAG workflow: scope validation -> hybrid retrieval -> entity expansion -> safe read-only graph query -> evidence ranking -> answer/citations; add retry and empty-result branches.|C7,C8,C9,V7,V8,V16,I.falkor_blog,I.harness|
|T10|x|Persist thread history/checkpoints with workspace-scoped FalkorDB saver or chat history adapter; define retention and cleanup; never persist provider secrets.|C3,C9,C11,V11,V16,I.falkor_blog,I.harness|
|T11|x|Define REST + SSE contract for chat, suggestions, feedback, context, source map, graph explanation, errors, cancellation, and degraded mode. Add contract fixtures.|C9,C11,V9,V10,V16,I.server,I.client,I.copilotkit,I.harness|
|T12|x|Integrate CopilotKit with self-hosted runtime: `/chat` route, workspace selector, strategy options (`auto`, `local`, `multi_path`), suggestions, AG-UI/SSE accumulation, abort handling, feedback, sources, and entity/source click navigation. Disable telemetry; never use hosted CopilotKit control plane.|C10,C11,V9,V10,V12,V16,I.client,I.routes,I.copilotkit,I.harness|
|T13|x|Add minimal internal ingestion UI and execution coordinator: local repo/document source form, progress/state, rejection report, refresh/delete controls, and workspace graph stats.|C1,C5,V4,V5,V16,I.routes,I.client,I.harness|
|T14|.|Keep existing graph explorer compatible: selected workspace can open graph overview/subgraph, citation can focus symbol/file, static `graph.json` path still works with `RAG_ENABLE=false`.|C10,V12,V13,V16,I.graph_json,I.routes,I.harness|
|T15|.|POST-HACKATHON: add shared-deployment auth/tenant policy, strict CORS/origin policy, rate limits, audit events, and formal provider-secret controls.|C3,C6,C8,V6,V15,V16,I.server,I.harness|
|T16|.|Add only MVP tests: cross-source and cross-workspace isolation, Cypher rejection, empty/degraded mode, SSE/AG-UI cancel, citation mapping, React chat behavior, ingestion lifecycle, and existing regression suite.|V4,V5,V6,V7,V8,V9,V10,V12,V13,V14,V16,I.harness|
|T17|.|Add Docker Compose dev stack with pinned FalkorDB version, seeded fixture workspace, mocked LLM mode, health checks, migration/reset docs, and optional provider setup.|C12,V14,V16,I.falkor_blog,I.config,I.harness|
|T18|.|POST-HACKATHON: add full observability, performance budgets, memory-growth tracking, and concurrent-workspace benchmarks.|V7,V14,V15,V16,I.harness|
|T19|.|POST-HACKATHON: document full threat model, provider retention, backup/restore, upgrade/rollback, credential rotation, and incident procedures.|C8,C9,V3,V6,V8,V15,V16,I.harness|
|T20|x|Build dynamic RAG harness and CI workflow. Replay T1-T4 as one workspace -> normalize -> validate -> FalkorDB upsert/read/delete scenario; emit JSON report; require fake and pinned-service modes.|V14,V16,I.harness,I.config|

## §B

|id|date|cause|fix|
|---|---|---|---|
|B1|2026-08-31|Windows held a native Vite dependency open during frozen pnpm reinstall|Stop only repo-owned Node processes and retry; no product invariant added because this is an external file-lock condition.|

Recommended hackathon order: finish T12 -> T13 -> T14 -> MVP slice of T16 -> T17. Defer T15, T18, and T19 until internal demo proves product value.
