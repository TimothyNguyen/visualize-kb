# Architecture — Target State

This doc synthesizes `architecture-current.md` + the four audits (`token-cost-analysis.md`, `persistence-analysis.md`, `graph-rendering-analysis.md`, and the query-path findings below) into a target design. It marks each mission-spec area as **gap → redesign** (deep-dived in a dedicated doc) or **keep as-is → cite current impl** (already solved; do not rebuild).

## Data model

**Gap → redesign.** No unified cross-repo entity identity today (`repo` is a flat node property, `cross_repo_types.py:54,67-69`) and no graph-schema/version field (only `built_at_commit`, `export.py:405-407`, a single git-commit stamp). Target model and migration in `cross-repo-design.md` (identity) and `migration-plan.md` Stage 1 (versioning).

## Query flow

**Gap → redesign.** Current: seed-score + BFS/DFS bounded by depth + token budget only, no ranking cutoff or intent classification (`serve.py:1187` `_query_graph_text`, full trace in `architecture-current.md` §2). Target pipeline in `query-engine-design.md`.

## Cross-repo model

**Gap → redesign.** Current: manual `merge-graphs` CLI + post-hoc `link_shared_type_declarations()` type-name matching (`cross_repo_types.py:1-76`). Target in `cross-repo-design.md`.

## Document model

**Partial gap → redesign.** Substrate exists (`FileType.DOCUMENT/PAPER/IMAGE`, `detect.py:25-29`) but no typed relationships (DESCRIBES/RATIONALE_FOR/etc.) or provenance fields connecting documents to code entities. Target in `document-knowledge-design.md`.

## Conversation model

**Partial gap → redesign.** kb-core-ui already has SQLite-backed conversation memory with typed kinds (`rule`/`lesson`/`business`/`overview`/`reference`, `API_CONTRACT.md:174`) and kb-core has a separate learning-loop sidecar (`reflect.py`). These are two unconnected systems today. Target separation + bridging in `memory-model.md`.

## AI-derived-knowledge trust model

**Keep as-is, extend.** The learning loop already has an outcome/trust vocabulary (`useful`/`dead_end`/`corrected`, time-decayed, `reflect.py`) — this is most of what mission §20's trust model asks for. The gap is narrow: it's a read-time overlay (`serve.py:59-65`) never merged into `graph.json`, so it can't yet be queried as graph state or promoted. `memory-model.md` covers extending this rather than replacing it.

## Persistence model

**Keep as-is (graph.json), extend selectively.** Full analysis in `persistence-analysis.md`: keep `graph.json` as the portable/canonical export; evaluate an additive SQLite index inside `kb_core` (mirroring kb-core-ui's `store.py`) for indexed lookup, feeding the query planner. No Neo4j/Redis.

## API changes

**Minor, deferred to implementation stages.** kb-core-ui's REST surface (`/graph/subgraph?symbol=:id&depth=2`, `API_CONTRACT.md:96-98`) already does bounded-context retrieval — the compact-serialization ask (mission §16) is largely met. Changes needed only as a side effect of the query planner (`query-engine-design.md`) and cross-repo scope parameter (`cross-repo-design.md`).

## Frontend changes

**Gap → redesign (rendering only).** `graph-rendering-analysis.md`: no progressive/hierarchical loading despite the community substrate already existing in `graph.json`. Wiring gap, not a missing-data gap.

## Migration strategy

See `migration-plan.md`. Sequencing note: graph versioning first (cheapest, unblocks safe iteration on everything else), then cross-repo identity, then the query planner, then the smaller document/memory/rendering wiring gaps.

## Risks

- **Scope creep risk**: most of the mission's 39-section wishlist is already implemented in some form (caching, document entities, compact serialization, token-cost tracking, learning loop, cross-repo linking). The main risk in executing this mission literally is re-implementing working systems instead of extending them. This doc set deliberately marks "keep as-is" wherever verified.
- **`cost.json` ambiguity**: referenced as a backup-worthy artifact name (`export.py:32`) with no confirmed writer in `kb_core/`. Any cost-instrumentation work should resolve this (implement or remove) before building on top of it — see `token-cost-analysis.md`.
- **Doc drift**: `ORCHESTRATION.md`/`kb-core-investigation.md` contain stale path references (see `architecture-current.md` closing note) — future doc updates should re-verify citations rather than propagating them.

## Alternatives rejected

- **Redis** — no distributed-cache requirement demonstrated; kb-core is local-first single-process.
- **Neo4j / other graph DB server** — no measured query-latency bottleneck justifies the operational cost; `graph.json` + an optional local SQLite index (see `persistence-analysis.md`) covers the identified gap.
- **Embeddings-by-default** — kb-core-ui's neural embedding path is already opt-in (`KB_CORE_UI_EMBED_URL`, `ORCHESTRATION.md:75-84`); no reason found to make it mandatory or to add embeddings to kb-core's structural graph queries, which tree-sitter/static analysis already answers deterministically.
- **Rewriting `graph.json` format wholesale** — too much existing tooling depends on it (export formats, merge-driver, manual inspection); extend via additive fields (version, identity keys) instead.
