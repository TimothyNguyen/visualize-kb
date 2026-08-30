# Memory Model — Current State & Target Design

## Two unconnected systems today (verified)

### System 1: kb-core-ui conversation memory (`kb-core-ui/python/kb_core_ui/memory/store.py`)

- SQLite `memories` table (`store.py:32-45`): `id`, `kind`, `title`, `text`, `source`, `created_at`, `embedder`, `dim`, `embedding` (BLOB, little-endian float32 — byte-compatible with the Go sidecar per the file's own docstring, `:1-6`: "Schema text is copied verbatim so a memory.db written by the Go binary opens unchanged, and vice versa").
- Typed kinds (`:19-25`): `KIND_RULE="rule"`, `KIND_LESSON="lesson"`, `KIND_BUSINESS="business"`, `KIND_OVERVIEW="overview"`, `KIND_REF="reference"` — `VALID_KINDS` tuple of all five.
- `Entry` dataclass (`:49-60`) is the read/write unit; `to_json_dict()` serializes for API responses.
- Retrieval is embedding-based: `Embedder`/`HTTPEmbedder`/`cosine()`/`embedder_from_env()` (`embedder.py:41,138,221,188`) — `HTTPEmbedder` calls an OpenAI-compatible `/embeddings` endpoint and returns a zero vector on failure (`embedder.py:139` docstring) rather than raising, so a down embedding service degrades retrieval quality silently rather than erroring the request. Default is a lexical `HashingEmbedder` (offline, no network) per `MIN_SCORE = 0.07` calibration note (`store.py:27-30`) — neural embeddings are opt-in via `KB_CORE_UI_EMBED_URL`, consistent with `architecture-target.md`'s "alternatives rejected: embeddings-by-default."
- This is a **separate SQLite file** from the structural index (`kb-core-ui/python/kb_core_ui/store.py` — files/symbols/unresolved_calls/edges tables, cited in `persistence-analysis.md`) — two different `store.py` modules under `kb_core_ui`, one for conversation memory, one for structural code lookup. Do not conflate them.

### System 2: kb-core learning-loop sidecar (`kb-core/kb_core/reflect.py`, `kb_core/querylog.py`)

- `querylog.py:log_query()` (`:43`) writes an opt-in JSONL query log (`_log_path()` `:15`, `nodes_from_result()` `:38`) — never persisted into `graph.json`.
- `reflect.py` aggregates outcome signals per node: `useful` / `dead_end` / `corrected` (module docstring `:4,7-11`). Score is a **time-decayed signed value**: `useful` positive, `dead_end`/`corrected` negative, `_DEFAULT_HALF_LIFE_DAYS = 30.0` (`:51`), `_decay()` (`:275-285`, `0.5 ** (age_days / half_life_days)`), signed accumulation at `:397-398`. A node is only "preferred" after corroboration (`_DEFAULT_MIN_CORROBORATION = 2`, `:52`) — a single `useful` marks it merely "tentative" (`:8`).
- Output artifacts: `render_lessons_md()` (`:489`) writes `LESSONS.md`; `write_learning_sidecar()` (`:824`) persists the aggregate; `load_learning_overlay()` (`:840`) reads it back.
- **Merge point confirmed**: `serve.py:58-65` — `_load_graph()` attaches the overlay as `G.graph["_learning_overlay"]` via `load_learning_overlay(resolved)` (`:62-63`), wrapped in a bare `try/except` that leaves the overlay `{}` on any failure (`:64-65`). Comment at `:58-60` states this is display-only annotation on `NODE` lines — **the overlay is never folded into `graph.json` itself**, so it doesn't survive a `merge-graphs` call, isn't queryable as graph state, and exists only for the single process that loaded it this way.
- `report.py:load_learning_for_report()` (`:40`) and `aggregate_lessons()` (`reflect.py:364`) are the other read paths (GRAPH_REPORT.md generation).

## Problem: two disconnected memory systems

- kb-core-ui's `memories` table answers "what has a human told the assistant to remember" (rules, lessons, business context, reference facts) — **explicit, user-authored** memory.
- kb-core's `reflect.py` sidecar answers "which graph nodes have proven useful/wrong across past queries" — **implicit, outcome-derived** memory, scoped to the graph itself, not to a conversation.
- Nothing bridges them: a `dead_end` outcome recorded by `reflect.py` isn't visible to kb-core-ui's memory retrieval, and a `rule`/`lesson` entry in kb-core-ui's SQLite has no link back to the graph nodes it might pertain to.
- Per mission §18-19 (external mission-prompt reference, not a repo file — see `cross-repo-design.md`'s note on this citation convention): the ask is a clean separation of transcript / working-memory / graph / query-cache / AI-derived-findings layers with defined promotion rules between them. Today's architecture has roughly two of those five (transcript+working-memory conflated in kb-core-ui's `memories` table; graph+query-cache+AI-findings conflated in kb-core's `querylog.py`+`reflect.py` pair), with no promotion path between the two systems.

## Target model

Keep the systems **separate but bridged**, not merged into one database (per `architecture-target.md`'s "AI-derived-knowledge trust model: keep as-is, extend" verdict — `reflect.py`'s outcome/trust vocabulary is already most of what's needed):

```
QueryRun          - one query/answer round-trip (question, resolved scope, seeds, timestamp)
RetrievalResult    - the subgraph/nodes returned for a QueryRun
Answer             - what was told to the user
Feedback           - useful/dead_end/corrected outcome tag on a QueryRun or Answer (reflect.py's existing vocabulary, formalized as an entity instead of an aggregate-only sidecar)
Correction         - the specific correction text when Feedback == corrected
```

- `QueryRun`/`RetrievalResult`/`Answer` are new entities that formalize what `querylog.py` already logs ad hoc (JSONL) into a structured shape reusable by both systems.
- `Feedback`/`Correction` generalize `reflect.py`'s existing outcome tags — same vocabulary (`useful`/`dead_end`/`corrected`), same time-decay model, but now addressable as entities a kb-core-ui `memories` row (kind=`lesson`) can reference, instead of being trapped in a graph-adjacent sidecar only `serve.py`'s overlay can see.
- Explicit sync boundary, not a merged database: kb-core-ui's `memories` table stays the system of record for user-authored rules/lessons; kb-core's `reflect.py` stays the system of record for outcome-derived graph-node trust. A `lesson` memory entry MAY cite a `QueryRun`/`Feedback` id as its `source` field (already a free-text column, `store.py:38`) — no schema change needed on the kb-core-ui side for this direction of the link.
- The gap this closes is narrow, matching `architecture-target.md`'s framing: "it's a read-time overlay never merged into `graph.json`, so it can't yet be queried as graph state or promoted." The fix is making the overlay's contents addressable (structured entities with ids) rather than rearchitecting either store.

## Migration path

1. Formalize `QueryRun`/`RetrievalResult`/`Answer` as structured records in `querylog.py`'s existing JSONL output (additive fields, not a format break) — gives `reflect.py` and any future kb-core-ui bridge a stable id to reference.
2. Keep `reflect.py`'s aggregation and half-life decay unchanged — it already does the harder part (time-decayed trust scoring) correctly; only the addressability of individual outcomes needs to change.
3. Add an optional `source` convention (e.g. `"kb-core:query_run:<id>"`) for kb-core-ui `memories.source` when a `lesson` is created from a kb-core query outcome — first real bridge, no schema migration on either side.
4. Do not merge the two SQLite files or run them through one query path — per `persistence-analysis.md` and `architecture-target.md`, this stays local-first and two-store, matching the existing kb-core-ui/kb-core split rather than introducing a shared memory service.
