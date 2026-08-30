# T15 handoff: cluster graphs + multigraph mode backport

Written 2026-08-30, mid-implementation, because the authoring session ran out of
context. This is a runbook for whoever picks the branch up next. It is in plain
English rather than the caveman notation `spec/SPEC.md` uses: the verification
sequence is order-dependent and comparison-based, and compression there buys
nothing worth the ambiguity.

## What T15 is

Backport of upstream Graphify-Labs/graphify PR #2134 into `kb-core`. Two coupled
features:

- **Cluster graphs** — compose N repos into one directed graph with declared
  cross-repo links (`api_call`, `shared_resource`, `mirrored_file`,
  `depends_on`, `references`), managed by `cluster init/add/remove/locate/build/
  check/status` and discoverable from inside a member repo through a
  `cluster-ref.json` marker plus a `--cluster [NAME]` flag on the read-only
  commands.
- **Multigraph mode** — preserve parallel edges between the same node pair
  through build, analysis, query and export, keyed by a content-derived
  `stable_edge_key` rather than NetworkX's positional 0/1/2.

Hard constraint, still in force: **multigraph is opt-in everywhere and default
single-repo behavior must not change.** Roughly 1100 existing kb-core tests
depend on the simple-graph path.

Branch `cluster-graph-backport`, cut off `perf-improve-v1` at `6c3f0e2`.

## Status at handoff

Phases 1 through 6 are complete and regression-verified. Phase 7 (tests) is
complete — all seven files written and green:

| File | Result |
| --- | --- |
| `kb-core/tests/cluster_helpers.py` | shared fixtures, no tests of its own |
| `kb-core/tests/test_cluster_spec.py` | 41 passed |
| `kb-core/tests/test_cluster_links.py` | 20 passed |
| `kb-core/tests/test_cluster_build.py` | 20 passed |
| `kb-core/tests/test_cluster_refs.py` | 28 passed |
| `kb-core/tests/test_cluster_cli.py` | 33 passed |
| `kb-core/tests/test_multigraph_build.py` | 21 passed |

Nothing is committed. The full plan this was executed from lives at
`~/.claude/plans/purring-squishing-sundae.md`.

## Working-tree inventory

Know what is T15 and what is not before staging anything.

**New, part of T15:**

- `kb-core/kb_core/cluster_ref.py`
- `kb-core/kb_core/cluster_graph.py`
- `kb-core/kb_core/cluster_cli.py`
- `kb-core/tests/cluster_helpers.py`
- `kb-core/tests/test_cluster_spec.py`
- `kb-core/tests/test_cluster_links.py`
- `kb-core/tests/test_cluster_build.py`
- `kb-core/tests/test_cluster_refs.py`
- `kb-core/tests/test_cluster_cli.py`
- `kb-core/tests/test_multigraph_build.py`

**Modified, part of T15:**

- `kb-core/kb_core/build.py`
- `kb-core/kb_core/global_graph.py`
- `kb-core/kb_core/cluster.py`
- `kb-core/kb_core/analyze.py`
- `kb-core/kb_core/affected.py`
- `kb-core/kb_core/export.py`
- `kb-core/kb_core/watch.py`
- `kb-core/kb_core/serve.py`
- `kb-core/kb_core/manifest_ingest.py`
- `kb-core/kb_core/cli.py`
- `kb-core/kb_core/__main__.py`

**Pre-existing and unrelated — do NOT commit with T15:**

- `kb-core-ui/web/package.json`
- `kb-core-ui/web/package-lock.json`
- `kb-core-ui/web/vite.config.ts`
- `kb-core-ui/web/public/kb-core-out/graph.json`
- `kb-core-ui/web/src/pages/GraphPageView.test.tsx`
- `kb-core-ui/web/src/test/`
- `spec/company-readiness-SPEC.md`

## Task 1 — DONE: `tests/test_multigraph_build.py`

```
cd kb-core
python -m pytest tests/test_multigraph_build.py -q
```

**21 passed** on 2026-08-30. Kept here as a map of what the file covers, since
the groups below are the ones most likely to break under future edits. Five
groups:

1. **`build_from_json` multigraph behavior.** Includes two tests that
   deliberately pin the *default*: `test_default_build_stays_simple` and
   `test_build_merge_defaults_to_simple_without_a_stored_flag`. Those two are
   the guard on the opt-in constraint — if either needs weakening to pass,
   something in the production code regressed, not the test.
2. **`stable_edge_key` determinism.** `test_key_survives_a_process_boundary`
   spawns a subprocess twice under `PYTHONHASHSEED=0` and `=1` and asserts one
   distinct result. It runs with `cwd` set to the `kb-core` package root so the
   child can import `kb_core`.
3. **`promote_to_multidigraph`** — direction is taken from the `_src`/`_tgt`
   markers, not from stored endpoint order.
4. **graph.json round trip** through `export.to_json` then
   `build.load_graph_json(preserve_type=True)`, asserting the `multigraph` flag
   persists and the edge keys survive.
5. **Community weight aggregation.** These two monkeypatch
   `kb_core.cluster.nx.community.louvain_communities` to capture the internal
   `stable` simple graph that `_partition` builds. That works because
   graspologic is **not installed** in this environment, so `_partition` always
   falls through to the Louvain branch. If graspologic ever lands here, the
   leiden branch needs stubbing too or these two will silently stop observing
   anything.

## Task 2 — Phase 8 verification

Run in this order.

**Step 1, targeted.** From `kb-core/`:

```
python -m pytest tests/test_cluster_spec.py tests/test_cluster_links.py tests/test_cluster_build.py tests/test_cluster_refs.py tests/test_cluster_cli.py tests/test_multigraph_build.py -q
```

**Step 2, full suite against baseline.** From `kb-core/`:

```
python -m pytest tests/ -q
```

Recorded baseline for this branch: **154 failed, 4404 passed, 173 skipped.**
Those 154 are pre-existing failures on `6c3f0e2`, not T15 damage.

Counts alone are not the gate. A regression that lands while an unrelated flake
clears reads as an unchanged count. Name-diff instead, against the baseline
worktree at `.worktrees/baseline` (a `git worktree` detached at `6c3f0e2`):

```
cd kb-core && python -m pytest tests/ -q 2>&1 | grep -oE "^FAILED tests/[^ ]+" | sort > /tmp/head.txt
cd ../.worktrees/baseline/kb-core && python -m pytest tests/ -q 2>&1 | grep -oE "^FAILED tests/[^ ]+" | sort > /tmp/base.txt
diff /tmp/base.txt /tmp/head.txt
```

Empty diff is the pass condition.

**Step 3, downstream import check.**

```
cd kb-core-ui && python -m pytest python/tests -q
```

`.github/workflows/parity.yml` only covers `kb-core-ui`, so this run is what
confirms T15 did not break a shared import.

## Already done — do not repeat

The manual end-to-end from the plan was executed and printed ALL OK: two
extracted fixture repos, `cluster init`, `cluster add` twice, one declared
`api_call` link, `cluster check` exiting 0, `cluster build` producing a composed
`kb-core-out/graph.json` plus `cluster-manifest.json` plus `CLUSTER_REPORT.md`
plus a `cluster-ref.json` in each member, then `query --cluster` resolving the
cluster graph from inside a member and `affected --cluster` crossing the repo
boundary via `calls_api`. It also confirmed `graph.json` is byte-stable across a
`--force` rebuild.

A 13-file CLI/hook regression run was name-diffed against the baseline worktree
and came back identical — 72 pre-existing failures on both sides.

## Known non-bugs

Do not re-investigate these.

- **`affected src/lib.rs --cluster` reports no unique node match.** In a composed
  cluster graph both members carry `src/lib.rs`, so the seed is genuinely
  ambiguous. Seed with a namespaced id instead: `affected crate_a::src_lib
  --cluster`. That path was verified to cross the repo boundary.
- **`explain lib.rs --cluster` picks one member's node without flagging
  ambiguity.** `find_node_ambiguity` compares `source_file`, which is identical
  across members. Pre-existing behavior on composed graphs, matches upstream,
  out of scope for T15.
- **`test_path_traverses_a_declared_link` builds its own cluster** instead of
  using the shared `two_member_cluster` fixture. With identical labels in both
  members the endpoint resolver picks a same-repo pair, and the shortest path
  between them never needs the declared cross-repo link. The bespoke fixture
  gives `beta` a distinct label so the assertion means what it says.

## Landing

Once Task 1 and Task 2 both pass:

1. Stage only the kb-core paths from the inventory above. Do not use `git add -A`
   — it would sweep in the unrelated `kb-core-ui/web` changes and
   `spec/company-readiness-SPEC.md`.
2. Commit.
3. Mark T15 done in `spec/company-readiness-SPEC.md`.
