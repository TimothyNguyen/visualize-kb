# Persistence — Current State vs. Target

## Current state

### kb-core: `graph.json` as canonical store
- `to_json()`, `kb_core/export.py:266` (verified), is the sole write path for the canonical graph artifact.
- Safety: a shrink guard (`export.py:267-321`, verified) refuses to overwrite an existing `graph.json` with fewer nodes unless `force=True` (bug `#479`) — fails safe on read errors and on an oversized existing file that trips the size cap.
- Pre-overwrite backups: `_BACKUP_ARTIFACTS` (`export.py:25-34`, verified) names artifacts to preserve via `backup_if_protected()` (`export.py:36`, verified) before a write replaces them.
- Format: NetworkX `node_link_data` (`export.py:326-328`, verified) with kb-core-specific enrichment (`community`, `community_name`, `norm_label`, `confidence_score`, restored edge direction from `_src`/`_tgt`) and canonicalized key ordering for stable diffs (`export.py:352-368`, verified).
- Every read (query, path, explain, benchmark) loads the **entire** `graph.json` into an in-memory `nx.Graph` — there is no indexed/partial-load path in `kb_core/` (see `architecture-current.md` §5.1).

### kb-core-ui: SQLite for structured lookups
- `kb-core-ui/python/kb_core_ui/store.py`: `files` (path/hash/language, line 19), `symbols` (line 25), `unresolved_calls` (line 44), `edges` (line 53) — all verified. This gives kb-core-ui indexed, incremental-by-hash lookups that `kb_core/`'s flat JSON does not have natively.

## Trade-off

`graph.json` is a good **portable export** (human-diffable-ish, tool-agnostic, easy to back up/version-control) but a poor **query substrate** at scale — every query pays full-file parse + full-graph-in-memory cost, and there's no indexed lookup by node ID, file, or repo without building an ad-hoc index in `serve.py` at load time.

kb-core-ui's SQLite tables prove the indexed-lookup pattern already works well enough in this codebase for structured queries (symbol/edge lookup by hash-keyed file).

## Target direction

Per the mission's own constraint (favor the simplest local architecture; no Redis/Neo4j without proven need) and kb-core's existing local-first posture:

- **Keep `graph.json` as the portable export format.** Don't remove it — it's the interchange format for `merge-graphs`, HTML/GraphML/Obsidian/Cypher export (`export.py`), and manual inspection.
- **Evaluate adding a SQLite-backed index inside `kb_core` itself** (mirroring kb-core-ui's `store.py` pattern) for node/edge lookup by ID, file, repo, and community — used by `serve.py` for indexed candidate lookup (feeds `query-engine-design.md`'s planner design) instead of a full in-memory graph scan on every query.
- `graph.json` would become the write-behind portable snapshot; SQLite becomes the queryable working store — the same two-layer split kb-core-ui already uses, applied to kb-core.
- Do not introduce a distributed store. Do not introduce embeddings-by-default for structural lookups — kb-core-ui's optional neural embedding (`ORCHESTRATION.md:75-84`) stays opt-in.

## Storage growth to model before committing to a design

Per the mission's §12 concern (avoid unbounded amplification): model a realistic scenario — a 100MB `graph.json`, 10 updates/day, 30 days, plus AST/semantic caches and `LESSONS.md` sidecars — and check whether `backup_if_protected()`'s backup-on-overwrite behavior (`export.py:36`) needs a retention cap. This is a measurement task for `performance-baseline.md`'s disk-bytes metric, not a design decision to make blind.
