# Migration Plan — Staged Implementation Order

Sequencing rationale (per `architecture-target.md`'s closing note): graph versioning first (cheapest, unblocks safe iteration on everything else), then cross-repo identity, then the query planner, then the smaller document/memory/rendering wiring gaps. Each stage below is independently shippable and independently reviewable — no stage requires a later stage to already exist, though later stages build on earlier ones' fields/edges.

This plan is **design/spec only** — this round produces no production code changes. `performance-results.md` stays a stub until an implementation round executes these stages.

## Stage 1 — Graph versioning

- **Scope**: add a schema/version field to `to_json()`'s output (`export.py:266-407`), alongside the existing `built_at_commit` stamp (`:405-407`). Additive field, not a replacement — `built_at_commit` (git-SHA) answers "what commit produced this," a new `graph_schema_version` answers "what shape is this JSON," which `built_at_commit` cannot (a schema change can happen without a commit to the *analyzed* repo).
- **Files touched**: `kb_core/export.py` (write path), `kb_core/build.py` / `kb_core/serve.py` (read paths that would need to tolerate a missing version field from pre-migration `graph.json` files — backward compatible read, not a hard requirement).
- **Review checkpoint**: confirm the shrink-guard (`export.py:267-321`) and `_BACKUP_ARTIFACTS` backup logic (`:25-34`) don't need version-awareness themselves (they operate on node counts and file names, not schema content — likely no change needed, verify before assuming).
- **Rollback**: version field is additive; a rollback simply stops writing it — no migration of existing `graph.json` files required.

## Stage 2 — Cross-repo identity (`cross-repo-design.md`)

- **Scope**: add `workspace_id`/`source_type`/`source_revision` as new optional node fields (`repository_id` as an alias write for today's `repo` property, not a rename). Fold `merge-graphs` + `link_shared_type_declarations()` into one pass, still manually triggered.
- **Files touched**: `kb_core/cross_repo_types.py`, `kb_core/cli.py` (`merge-graphs` command), `kb_core/build.py` (node field additions).
- **Review checkpoint**: verify no existing consumer of the `repo` property (search all of `kb_core/` and `kb_core_ui/`) breaks when `repository_id` appears alongside it — this is additive metadata per `cross-repo-design.md`'s migration path step 1.
- **Depends on**: Stage 1's version field is a good place to also bump when the identity model changes — bundle only if convenient, not required.
- **Rollback**: new node fields are additive; unset them to roll back, no `repo` property removal ever happens.

## Stage 3 — Query planner (`query-engine-design.md`)

- **Scope**: score-threshold traversal cutoff on `_bfs`/`_dfs` (`serve.py:924`/`955`), intent classification pre-step, unification of `benchmark.py`'s `_query_subgraph_tokens()` with `serve.py`'s real scoring path.
- **Files touched**: `kb_core/serve.py`, `kb_core/benchmark.py`.
- **Review checkpoint**: run `bench_query_scoring.py`'s existing `_verify_equality()` harness (`tests/bench_query_scoring.py:153`) style check between old and new traversal behavior to catch unintended relevance-ranking regressions — the project already has this discipline for the legacy/optimized scoring pair; extend it to cover the new cutoff logic too.
- **Depends on**: Stage 2's `repository_id`/`workspace_id` fields, if cross-repo scope widening (repo → deps → related → workspace) is included in this stage's intent-classification/scope-resolution step. Can ship the score-cutoff and benchmark-unification parts independently of the cross-repo-scoping part if sequencing needs to split further.
- **Rollback**: score-threshold cutoff should default to today's depth-only behavior (opt-in parameter) — safe to ship dark and roll back by not enabling it.

## Stage 4+ — Document model, memory entities, progressive rendering

These three are independent of each other and can be sequenced in any order after Stage 1-3, or in parallel across different engineers:

- **4a. Document knowledge model** (`document-knowledge-design.md`): `Section` node between `Document` and its extracted entities (markdown/rst only, first pass), `DESCRIBES` as the first new typed relation. Files: `kb_core/build.py`, `kb_core/llm.py` (document extraction path).
- **4b. Memory-model bridging** (`memory-model.md`): formalize `QueryRun`/`RetrievalResult`/`Answer` in `querylog.py`'s JSONL output; add the `source` convention on kb-core-ui `memories.source` for lesson-from-query-outcome linking. Files: `kb_core/querylog.py`, `kb-core-ui/python/kb_core_ui/memory/store.py` (no schema change — `source` is already a free-text column).
- **4c. Progressive rendering** (`graph-rendering-analysis.md`): wire `GlobalGraph.tsx`'s rendering to the already-computed `community`/`community_name` fields (`export.py:333-337`) for a community-level default view, plus a node-count cap fallback above which the full-graph layout doesn't run. Files: `kb-core-ui/web/src/components/GlobalGraph/GlobalGraph.tsx`, possibly a new community-summary API endpoint alongside the existing `/graph/subgraph` route.

## Stage checkpoints common to all stages

- Every stage adds fields/relations additively — no stage in this plan requires rewriting `graph.json`'s format wholesale (per `architecture-target.md`'s "alternatives rejected").
- Every stage's review checkpoint should re-run `kb-core benchmark` (`performance-baseline.md`'s methodology) after Stage 3 specifically unifies the benchmark's scoring path with production — before Stage 3, benchmark numbers measure a different algorithm than production queries use, so don't treat pre-Stage-3 benchmark deltas as representative of query-planner changes.
- `performance-results.md` populates only after a stage is implemented and benchmarked — never populated speculatively ahead of implementation.

## Explicit non-goals for this migration

- No Redis, no Neo4j, no mandatory embeddings at any stage (per `architecture-target.md`'s alternatives-rejected list) — these were considered and rejected for lack of a demonstrated need, not overlooked.
- No stage merges kb-core-ui's conversation-memory SQLite with kb-core's `reflect.py` sidecar into one database (`memory-model.md`'s explicit-sync-boundary recommendation).
- No stage infers a cross-repo or document-relationship edge from name/label similarity alone without a deterministic evidence source (manifest, import statement, explicit heading/entity match) — per `cross-repo-design.md` migration step 4 and `document-knowledge-design.md`'s `DESCRIBES` caution.
