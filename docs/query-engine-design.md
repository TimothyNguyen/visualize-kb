# Query Engine — Current State & Target Design

## Current implementation (`kb_core/serve.py`, verified)

Entry point `_query_graph_text()` (`serve.py:1187-1246`, read in full):

1. `_query_terms(question)` (`:262`) — tokenize the question.
2. `_score_query(G, terms, collect_per_term_seeds=True)` (`:462`) — single scoring pass over the whole graph that produces both the combined ranking and per-term singleton winners. The docstring/comment at `:1198-1203` notes this was previously **T+1 passes** (one combined + one per query token, each re-walking the whole graph) — on a 100k-node, three-term benchmark ~71% of scoring time was spent in the redundant per-term passes. Fixed, but the underlying model is still a single full-graph scoring pass, not an indexed lookup.
3. Relational-intent-verb filtering (`:1205-1217`) — strips verbs like "calls"/"uses" from the per-term seed *guarantee* (bug `#2507`: an incidental verb match could otherwise seat a decoy BFS root) while leaving them in the ranked list so a genuine identifier named after a verb can still win a seat on merit.
4. `_pick_seeds(qs.ranked, G=G, best_seed_by_term=best_seed_by_term)` (`:656`) — selects BFS/DFS start nodes from the ranking.
5. `_resolve_context_filters(question, context_filters)` (`:847`) + `_filter_graph_by_context(G, resolved_filters)` (`:857`) — optional pre-traversal graph filtering (e.g. by node kind).
6. `_bfs(traversal_graph, start_nodes, depth)` (`:924`) or `_dfs(...)` (`:955`), selected by `mode` — traversal is **depth-bounded only**. No score-based cutoff, no early termination on relevance decay.
7. `_subgraph_to_text(traversal_graph, nodes, edges, token_budget, seeds=start_nodes)` (`:982`) — serializes the resulting subgraph to text, truncating to `token_budget`, with seeds ordered first so they survive truncation (bug `#BUG2`: a branch merge had silently dropped the `seeds=` argument, making seed-first ordering dead code — now restored and comment-guarded at `:1243-1245`).

Supporting lookups: `_find_node_tiers()` (`:1249`), `_find_node()` (`:1327`), `_shortest_path_text()` (`:1365`) — used by `graphify path`/`explain` rather than the main query flow.

Every call operates on the full in-memory `nx.Graph` (loaded from `graph.json` — see `persistence-analysis.md`); there is no indexed candidate pre-filter before scoring, and no query-intent classification before choosing `mode`/`depth`/`context_filters` (those are caller-supplied, not planner-derived).

## Problems vs. mission's query-planner ask

1. **No ranked cutoff.** Traversal is bounded by `depth` and by `token_budget` at the *serialization* step, not by a relevance-score threshold during traversal — a low-relevance node within `depth` hops of a seed is included, then may or may not survive truncation depending on serialization order, rather than being pruned during the walk.
2. **No intent classification.** `mode` (bfs/dfs), `depth`, and `context_filters` are passed in by the caller (CLI flags / MCP tool args); nothing in `serve.py` infers "this looks like a relationship question, use DFS with context_filter=['call']" from the question text itself — beyond the narrow relational-intent-verb carve-out at `:1205-1217`, which only protects seed selection, not mode/depth choice.
3. **No indexed candidate lookup.** `_score_query` walks every node on every query (`:462`); there is no ID/file/repo/community index consulted first to shrink the candidate set before scoring (this is the gap `persistence-analysis.md`'s proposed SQLite index would close).
4. **Duplicate/competing scoring implementations.** `kb_core/benchmark.py`'s `_query_subgraph_tokens()` (`benchmark.py:37-73`) reimplements a simplified, independent BFS+scoring pass — naive substring scoring, top-3 seeds — rather than calling `serve.py`'s real `_score_query`/`_pick_seeds`/`_bfs`. This means the benchmark measures a different (simpler) algorithm than what users actually query with, so `reduction_ratio` numbers in `performance-baseline.md` do not necessarily reflect production query behavior.
5. **The codebase already tracks this divergence risk itself**: `kb-core/tests/bench_query_scoring.py` (found via `graphify query` orientation) is a dedicated harness comparing `_legacy_score_and_pick()` (`:101`) against `_optimized_score_and_pick()` (`:122`) with an explicit `_verify_equality()` check (`:153`), `_build_random_graph()` (`:67`), `_load_real_graph()` (`:87`), `_run_scenario()` (`:182`), `main()` (`:226`). This confirms the project already treats "two scoring implementations silently diverging" as a known risk class for the *legacy-vs-optimized* pair inside `serve.py` itself — the same discipline has not yet been extended to `benchmark.py`'s separate reimplementation.

## Target pipeline

```
question
  -> intent classification (structural lookup / relationship / broad exploration / "why" narrative)
  -> scope resolution (repo / workspace — depends on cross-repo-design.md's identity model)
  -> candidate lookup (indexed by id/file/repo/community — depends on persistence-analysis.md's SQLite index)
  -> bounded traversal (depth AND score-threshold bounded, not depth-only)
  -> ranking (reuse _score_query's single-pass model; extend cutoff semantics rather than replacing it)
  -> compact subgraph serialization (existing _subgraph_to_text, unchanged)
```

Design principles:

- **Reuse `_score_query`'s single-pass optimization** (`:462`, `:1198-1203`) — it already solved the T+1-pass performance bug; the target design adds a score-threshold traversal cutoff on top of it, not a replacement scoring engine.
- **Intent classification is a new, narrow addition** ahead of step 5's mode/depth/context_filter selection — a lightweight classifier (keyword/pattern based, consistent with the mission's "avoid embeddings-by-default" constraint and `architecture-target.md`'s alternatives-rejected list) that maps question shape to `(mode, depth, context_filters)` defaults, with the caller-supplied values (today's only path) still available as an override.
- **Indexed candidate lookup is a scope-reduction step inserted before `_score_query`**, not a replacement for it — for large graphs, resolve scope (repo/workspace) and consult the SQLite index proposed in `persistence-analysis.md` to shrink the node set handed to `_score_query`, rather than always scoring the full `nx.Graph`.
- **Unify `benchmark.py`'s scoring path with `serve.py`'s real path.** `_query_subgraph_tokens()` (`benchmark.py:37-73`) should call the same `_score_query`/`_pick_seeds`/`_bfs` functions `serve.py` uses (via a shared internal API), rather than maintaining a second, simpler reimplementation — closing the same divergence-risk class that `bench_query_scoring.py` already guards against for the legacy/optimized pair inside `serve.py` itself.
- **Cross-repo scope widening** (current repo → dependency repos → related repos → full workspace, per `cross-repo-design.md`) plugs into the "scope resolution" stage above; it requires `cross-repo-design.md`'s identity fields (`workspace_id`, `repository_id`) to exist first, which is why `migration-plan.md` sequences cross-repo identity before the query planner.

## Migration path

1. Add score-threshold traversal cutoff to `_bfs`/`_dfs` (`:924`/`:955`) as an additive parameter, default off (preserves current depth-only behavior for existing callers) — cheapest, most isolated change.
2. Add intent classification as a pre-step feeding `_query_graph_text`'s existing `mode`/`depth`/`context_filters` parameters — no signature-breaking change, classifier output becomes the default when the caller doesn't specify them explicitly.
3. Unify `benchmark.py`'s `_query_subgraph_tokens()` with `serve.py`'s real scoring/traversal functions — do this before publishing any new `performance-baseline.md` numbers under the target design, since the current benchmark measures a different algorithm than production queries use.
4. Indexed candidate lookup (SQLite-backed) is the largest change and depends on `persistence-analysis.md`'s index existing — sequence last, per `migration-plan.md`.
