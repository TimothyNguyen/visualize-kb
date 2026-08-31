# Workspace GraphRAG Chatbot Manager

## §G

G1. Turn KB Core graph JSON plus document corpora into workspace-scoped FalkorDB knowledge graphs, then answer repo, docs, and cross-repo questions in existing React UI through a stateful GraphRAG chatbot.

G2. Keep current local graph explorer working without FalkorDB. GraphRAG is opt-in backend capability; no browser talks to FalkorDB directly.

## §C

C1. Sources: local repo, GitHub repo URL + branch/commit, uploaded document set, document URL, or many sources combined in one workspace.

C2. Repo source starts from KB Core `graph.json`; document source uses GraphRAG-SDK-compatible extraction into the same normalized graph envelope.

C3. One FalkorDB graph per workspace. Every node, edge, chunk, citation, and chat checkpoint also carries `workspace_id` and `source_id` defense-in-depth metadata.

C4. Ingestion idempotent by source content hash + extractor/schema version. Re-run unchanged source = no duplicate graph facts or embeddings.

C5. Source refresh removes stale facts/chunks owned by that source only. It never deletes facts owned by another source in same workspace.

C6. FalkorDB graph names derive from validated workspace IDs. User input never becomes raw Cypher, graph name, label, or relationship type without validation.

C7. Retrieval combines lexical/vector candidate search with bounded graph traversal. Vector-only fallback allowed only when graph retrieval unavailable; response marks degraded mode.

C8. Generated Cypher is read-only, parameterized, schema-constrained, timeout-bounded, and executed with read-only credentials. No chat path can mutate FalkorDB.

C9. Chat answer includes source citations and retrieval metadata. Unsupported claim -> explicit insufficient-evidence response.

C10. Existing `graph.json`, graph REST/MCP routes, SQLite stores, and current Graph/Bots/Memory UI flows remain backward compatible.

C11. `@falkordb/ui-chat` is presentation layer only. Backend owns workspace scope, retrieval, authorization boundary, citations, persistence, and stream protocol.

C12. FalkorDB Cloud and local Docker use same adapter/config contract. Missing FalkorDB or LLM config fails RAG health checks clearly; base graph UI still starts.

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

I.falkor_ui. `https://github.com/FalkorDB/falkordb-ui` — reference UI package: `@falkordb/ui-chat`, `onQuery`, streaming, suggestions, sources, `explainGraph`, `sourceMap`, strategy picker, feedback.

I.config. `FALKORDB_URL`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `FALKORDB_SSL`, `RAG_LLM_PROVIDER`, `RAG_LLM_MODEL`, `RAG_EMBEDDING_MODEL`, `RAG_MAX_CONTEXT`, and `RAG_ENABLE` — server-only configuration; secrets never enter frontend bundle.

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
|T5|.|Implement idempotent source reconciler: manifest/hash check, transactional staging, source-owned stale deletion, retry convergence, publish marker, and rollback/recovery handling.|C4,C5,V4,V5,V16,I.harness|
|T6|.|Implement repo ingestion from KB Core JSON and document ingestion using GraphRAG-SDK-compatible loaders/chunking/entity-relation extraction. Emit same normalized envelope for both.|C1,C2,V1,V3,V16,I.extract,I.falkor,I.harness|
|T7|.|Load `GraphDocument`-equivalent facts through `FalkorDBGraph`; create versioned full-text/vector indexes; embed chunk text and selected graph properties through `FalkorDBVector` hybrid search.|C2,C7,V3,V7,V16,I.falkor_blog,I.harness|
|T8|.|Add workspace CLI/API: list/create/delete workspace, add/remove/refresh sources, start/cancel ingestion, run status, health, stats, and bounded graph/subgraph context.|C1,C3,C5,V4,V6,V16,I.server,I.cli,I.harness|
|T9|.|Build LangGraph RAG workflow: scope validation -> hybrid retrieval -> entity expansion -> safe read-only graph query -> evidence ranking -> answer/citations; add retry and empty-result branches.|C7,C8,C9,V7,V8,V16,I.falkor_blog,I.harness|
|T10|.|Persist thread history/checkpoints with workspace-scoped FalkorDB saver or chat history adapter; define retention and cleanup; never persist provider secrets.|C3,C9,C11,V11,V16,I.falkor_blog,I.harness|
|T11|.|Define REST + SSE contract for chat, suggestions, feedback, context, source map, graph explanation, errors, cancellation, and degraded mode. Add contract fixtures.|C9,C11,V9,V10,V16,I.server,I.client,I.falkor_ui,I.harness|
|T12|.|Integrate `@falkordb/ui-chat`: custom element typings, `/chat` route, workspace selector, strategy options (`auto`, `local`, `multi_path`), suggestions, SSE accumulation, abort handling, feedback, sources, and entity/source click navigation.|C10,C11,V9,V10,V12,V16,I.client,I.routes,I.falkor_ui,I.harness|
|T13|.|Add ingestion UI: source add form, repo branch/commit fields, document upload/URL, progress/state, rejection report, refresh/delete controls, and workspace graph stats.|C1,C5,V4,V5,V16,I.routes,I.client,I.harness|
|T14|.|Keep existing graph explorer compatible: selected workspace can open graph overview/subgraph, citation can focus symbol/file, static `graph.json` path still works with `RAG_ENABLE=false`.|C10,V12,V13,V16,I.graph_json,I.routes,I.harness|
|T15|.|Add auth boundary hook and tenant policy interface before shared deployment: workspace authorization callback, server-side scope checks, CORS/origin policy, rate limits, body/upload limits, provider secret redaction, audit events.|C3,C6,C8,V6,V15,V16,I.server,I.harness|
|T16|.|Add tests: normalizer goldens, duplicate/retry/delete reconciliation, cross-source and cross-repo retrieval, workspace isolation, Cypher validator, empty/degraded mode, SSE cancel, React chat behavior, and existing regression suite.|V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13,V14,V16,I.harness|
|T17|.|Add Docker Compose dev stack with pinned FalkorDB version, seeded fixture workspace, mocked LLM mode, health checks, migration/reset docs, and optional provider setup.|C12,V14,V16,I.falkor_blog,I.config,I.harness|
|T18|.|Add observability and performance gates: fixture budgets for ingestion, hybrid retrieval, graph expansion, first token, complete answer, memory growth, and concurrent workspace isolation. Record baseline before rollout.|V7,V14,V15,V16,I.harness|
|T19|.|Document threat model, data flow, provider retention assumptions, prompt-injection handling, source trust labels, backup/restore, graph reset, upgrade, and rollback procedures.|C8,C9,V3,V6,V8,V15,V16,I.harness|
|T20|x|Build dynamic RAG harness and CI workflow. Replay T1-T4 as one workspace -> normalize -> validate -> FalkorDB upsert/read/delete scenario; emit JSON report; require fake and pinned-service modes.|V14,V16,I.harness,I.config|

## §B

|id|date|cause|fix|
|---|---|---|---|

Recommended order: T1 -> T2 -> T3+T4 -> T20 -> T5+T6 -> T7 -> T8 -> T9+T10+T11 -> T12+T13+T14 -> T15+T16 -> T17+T18+T19.
