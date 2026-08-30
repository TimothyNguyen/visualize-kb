# Cross-Repo Identity & Linking — Target Design

## Current state (verified, `cross_repo_types.py` read in full — 76 lines)

- Cross-repo linking is a two-step manual process:
  1. `merge-graphs` (CLI, `cli.py`) merges two or more `graph.json` files, prefixing every node ID with a repo tag.
  2. `link_shared_type_declarations()` (`cross_repo_types.py:32-75`) then adds a `same_type_as` edge (`SHARED_TYPE_RELATION`, line 29) between type-declaration nodes that share a `(namespace, label)` key and come from different repos (`:40-55`). Edges only — no node merging, so drift between two repos' copies of a shared contract stays visible (`:17-19` docstring rationale).
- Matching requires: node has `_callable_class` + `source_file` (`:42`), a non-empty `metadata.namespace` and `label` (`:44-46`), and a `repo` property (`:46`). Confidence is fixed at `INFERRED`/`0.9` (`:67-68`) — never `EXTRACTED` or user-confirmed.
- Repo identity today is **one flat string property** (`repo`) on each node (`:54,58`) — no revision/commit, no source-type distinction (code vs. document), no workspace grouping above the repo level.
- This pass runs **after** the pipeline, invoked manually — not part of `detect→extract→build→cluster→export`.

## Problems

1. No unified identity — `repo` alone can't distinguish two different clones/branches/revisions of the same repo, or scope a query to "this workspace" vs. "this repo."
2. Manual invocation — an operator must remember to run `merge-graphs` + the linking pass; nothing in `watch.py`'s incremental-update path re-links automatically when either side's graph changes.
3. Type-name matching only — no equivalent for API-call, event-produce/consume, or schema-read/write relationships (mission §8's `CALLS_API`/`DEPENDS_ON`/`PRODUCES_EVENT`/etc.).
4. No adaptive query scoping — because there's no workspace/repo hierarchy, a query can't "widen" from repo → dependencies → workspace; today it's single-graph or fully-merged, nothing in between.

## Target identity model

Add explicit identity fields (additive — extend node schema, don't replace `repo`):

```
workspace_id      - groups repos being explored together (defaults to a stable hash of the merge set, or explicit config)
source_type       - "code" | "document" | "schema" | ...
repository_id     - stable id for the repo (today's `repo` tag, formalized)
source_revision   - commit sha / doc revision hash the extraction ran against (kb-core already computes git HEAD for `built_at_commit`, export.py:405 — reuse that mechanism per-repo instead of per-merged-output)
entity_id         - today's normalize_id() output (ids.py:50-83), unchanged
```

Composite key for cross-repo-safe identity: `(workspace_id, source_type, repository_id, source_revision, entity_id)`. This is additive metadata on existing nodes, not a new ID scheme — `entity_id` stays what `normalize_id()` already produces; the other fields disambiguate when the same `entity_id` could plausibly collide across repos (rare after namespace-qualification, but the model should not rely on that being rare).

## Cross-repo edge types

Extend beyond `same_type_as` with typed, provenance-carrying edges per mission §8:

- `CALLS_API` — caller references an endpoint another repo's service implements
- `DEPENDS_ON` — package/module dependency across repos
- `IMPLEMENTS_INTERFACE`
- `PRODUCES_EVENT` / `CONSUMES_EVENT`
- `READS_SCHEMA` / `WRITES_SCHEMA`
- `SHARES_CONTRACT` (generalizes today's `same_type_as` — keep `same_type_as` as the specific type-declaration case, add the others as new relations following the same "edges only, confidence-scored, provenance-preserving" pattern already established in `cross_repo_types.py`)

Each new edge type should reuse the existing edge shape (`relation`, `context`, `confidence`, `confidence_score`, `source_file`, `_src`/`_tgt`) — no new edge schema needed, only new relation values and new detection passes analogous to `link_shared_type_declarations()`.

## Adaptive scope widening

Query scope should default narrow and widen only on insufficient results:

```
current repo → direct dependency repos (via DEPENDS_ON edges) → related repos (via any cross-repo edge) → full workspace
```

This is a `query-engine-design.md` concern (the planner decides when to widen) but depends on the identity model above existing first — you can't scope to "direct dependencies" without a `DEPENDS_ON` edge type and a `repository_id` to scope by.

## Migration path from current state

1. Add `workspace_id`/`source_revision` as new optional node fields; leave `repo` in place (rename is not required — `repository_id` can be an alias write, not a breaking rename).
2. Fold `merge-graphs` + `link_shared_type_declarations()` into the same pass, still manually triggered for now — automatic re-linking on `watch.py` changes is a later stage once the manual path is proven.
3. Add one new cross-repo edge type at a time (start with `DEPENDS_ON`, since dependency manifests are the most deterministic signal to extract, unlike `CALLS_API` which requires endpoint-string matching heuristics) rather than building all edge types at once.
4. Never infer an authoritative dependency from name-matching alone (mission §8 explicit warning) — every new edge type needs its own evidence source (manifest file, import statement, schema reference), not just label similarity.
