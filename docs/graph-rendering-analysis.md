# Graph Rendering — Current State & Analysis

## Current implementation

- `kb-core-ui/web/src/components/GlobalGraph/GlobalGraph.tsx` (verified, read in full) — React + `@xyflow/react` (`ReactFlow`, `Background`, `Controls`, `MiniMap`, line 2).
- Layout: `layoutWithDagre()` from `web/src/utils/dagreLayout.ts` — a deterministic tree/DAG layout (Dagre), not a force-directed physics simulation. Runs synchronously on the main thread inside a `useMemo` (`GlobalGraph.tsx:79-103`) recomputed whenever `visibleNodes`/`visibleEdges`/`centerId`/`roleById`/`coreIds` change.
- The `<ReactFlow>` element is **remounted** (`key={scope:centerId}`, `GlobalGraph.tsx:127`) on every scope or focus change specifically to force `fitView` to rerun — by design (comment at `:122-126` explains `fitView` only fires once on mount). This means a full graph rebuild + re-layout + re-render on every scope switch, not an incremental view update.
- **No node-count cap, virtualization, or level-of-detail gating found.** The "All" scope option (`GlobalGraph.tsx:111`) renders every `symbolNode` passed in; the only reduction mechanism is the manual directory-based `scope` filter (`GlobalGraph.tsx:51-77`), which still includes one-hop neighbors of the selected directory (dimmed) rather than a hard node limit.
- Node roles (`entry`/`leaf`/`normal`) are derived once per render from the **full** edge set (`GlobalGraph.tsx:34-49`), independent of scope — a reasonable design (role is a whole-repo property) but confirms the component always holds the entire node/edge arrays in memory regardless of what's visible.

## Substrate already available for progressive rendering

- `kb_core/cluster.py` already computes communities: `_partition()` (Louvain-style via networkx), `label_communities_by_hub()`, main `cluster()` entry, and `remap_communities_to_previous()` for ID stability across rebuilds (approximate ranges from prior trace: `cluster()` ~134-238, hub labeling ~86-112, remap ~272+ — not re-verified line-exact this pass).
- `export.py:333-337` (verified) already writes `community` and `community_name` onto every node in `graph.json`.
- **This means the hierarchy substrate the mission's §25 "hierarchical/progressive rendering" asks for already exists in the data** — it just isn't used by `GlobalGraph.tsx` today. The frontend's only grouping today is directory-path-derived (`dirOf()`, `GlobalGraph.tsx:13-16`), not the community structure kb-core already computes.

## Gap vs. mission §25-28

| Ask | Status |
|---|---|
| Progressive/hierarchical loading (workspace → repo → community → module → symbol) | Missing — frontend loads one flat node/edge list; no level switching |
| Viewport culling | Missing — no evidence found |
| Initial-load node cap (mission suggests <=200-500) | Missing — no cap found; relies on manual scope filter |
| Search performance at scale | Out of scope of `GlobalGraph.tsx` — not reviewed this pass (would need a separate search-component audit) |
| Avoid re-running layout on unrelated state changes (e.g. chat streaming) | Partially at risk — `GlobalGraph` is scope/centerId-keyed, so a graph remount is triggered specifically by graph-relevant state, not chat state, but this file doesn't show whether a parent component re-renders `GlobalGraph` on chat updates; needs a parent-tree check before concluding this is safe |

## Recommendation direction (design only)

1. Use the already-computed `community`/`community_name` fields from `graph.json` as the first level of a progressive load: default view = communities only (or top-N hub nodes per community via `god-nodes`-style ranking), expand a community into its member symbols on click, rather than loading every symbol up front.
2. Add an explicit node-count cap on the initial/"All" scope render, falling back to the community-level view above the cap instead of laying out the full graph.
3. Don't introduce a new clustering computation for the frontend — `cluster.py`'s output is already the hierarchy substrate; the gap is wiring, not missing data.
4. Don't migrate off `@xyflow/react`/Dagre without a measured bottleneck — no benchmark in this pass shows current rendering is too slow, only that it has no ceiling. `performance-baseline.md` should measure render latency at the defined graph-size tiers before any rendering-library change is considered.
