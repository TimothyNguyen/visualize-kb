# Low-Risk Graph Performance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit graph compatibility metadata and make performance measurements use production query behavior, without changing default query behavior or storage architecture.

**Architecture:** Keep `graph.json` as portable canonical export. Add one additive schema field at export time. Extract one shared query execution helper from `serve.py` so production queries and benchmarks use identical scoring, seed selection, filtering, traversal, and edge completion. Add a read-only runtime benchmark for latency, memory, and disk measurements.

**Tech Stack:** Python 3.10+, NetworkX, pytest, existing `kb_core.export`, `kb_core.serve`, `kb_core.benchmark`, and `kb_core.paths` modules.

**Spec:** `docs/migration-plan.md`, `docs/persistence-analysis.md`, `docs/query-engine-design.md`, `docs/performance-baseline.md`, and `docs/performance-results.md`.

## Global Constraints

- Graph changes are additive; preserve existing `links`/`edges` normalization and `built_at_commit`.
- Default query behavior remains depth-bounded BFS/DFS; no score cutoff or intent-default change in this plan.
- Benchmark production query behavior; do not publish measurements from the old simplified benchmark path.
- Keep `graph.json` as portable export; do not add Redis, Neo4j, or mandatory embeddings.
- Do not merge `kb-core-ui` static JSON and SQLite graph authority in this plan.
- Do not stage generated `kb-core-out`, graph JSON, cache, virtualenv, memory, reflection, or fixture `obj` files.
- Use `python -m pytest` only after installing dev dependencies; missing pytest is a setup failure, not a passing test run.

---

### Task 1: Add Graph Schema Version

**Files:**
- Modify: `kb-core/kb_core/export.py:25-407`
- Test: `kb-core/tests/test_export.py`
- Test: `kb-core/tests/test_serve.py`

**Interfaces:**
- Existing `to_json(G, communities, output_path, force=False, built_at_commit=None, community_labels=None)` stays unchanged.
- New public constant: `kb_core.export.GRAPH_SCHEMA_VERSION = 1`.
- New graph files contain top-level integer `graph_schema_version`.
- Readers accept old graph files without this field.

- [ ] **Step 1: Add failing export test**

Add beside `test_to_json_valid_json`:

```python
from kb_core.export import GRAPH_SCHEMA_VERSION


def test_to_json_includes_graph_schema_version(tmp_path):
    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.json"

    assert to_json(G, communities, str(out), built_at_commit="test-commit")

    data = json.loads(out.read_text())
    assert data["graph_schema_version"] == GRAPH_SCHEMA_VERSION
    assert isinstance(data["graph_schema_version"], int)
    assert data["built_at_commit"] == "test-commit"
```

- [ ] **Step 2: Add failing legacy-reader test**

Add beside existing graph-loading tests in `kb-core/tests/test_serve.py`:

```python
def test_load_graph_accepts_graph_without_schema_version(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(
            {
                "directed": False,
                "nodes": [{"id": "legacy", "label": "legacy"}],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    graph = _load_graph(str(graph_path))

    assert list(graph.nodes) == ["legacy"]
```

- [ ] **Step 3: Run focused tests and verify initial failure**

```bash
python -m pytest kb-core/tests/test_export.py::test_to_json_includes_graph_schema_version kb-core/tests/test_serve.py::test_load_graph_accepts_graph_without_schema_version -q
```

Expected: export test fails because `GRAPH_SCHEMA_VERSION` is undefined. Legacy test must pass after implementation.

- [ ] **Step 4: Implement additive field**

In `kb-core/kb_core/export.py`, define near `_BACKUP_ARTIFACTS`:

```python
GRAPH_SCHEMA_VERSION = 1
```

In `to_json`, after node-link enrichment and before the existing commit stamp:

```python
data["graph_schema_version"] = GRAPH_SCHEMA_VERSION
```

Do not change shrink-guard ordering, backup behavior, field sorting, edge direction restoration, atomic writes, or `built_at_commit`.

- [ ] **Step 5: Run regression tests**

```bash
python -m pytest kb-core/tests/test_export.py kb-core/tests/test_serve.py -q
```

Expected: all tests pass, including old graph loading without the version field.

- [ ] **Step 6: Commit**

```bash
git add kb-core/kb_core/export.py kb-core/tests/test_export.py kb-core/tests/test_serve.py
git diff --cached --check
git commit -m "Add graph schema version to exports"
```

---

### Task 2: Share Production Query Execution With Benchmark

**Files:**
- Modify: `kb-core/kb_core/serve.py:462-1246`
- Modify: `kb-core/kb_core/benchmark.py:1-82`
- Test: `kb-core/tests/test_serve.py`
- Test: `kb-core/tests/test_benchmark.py`

**Interfaces:**
- New private result type in `serve.py`:

```python
class QueryExecution(NamedTuple):
    start_nodes: list[str]
    nodes: set[str]
    edges: list[tuple]
    resolved_filters: list[str]
    filter_source: str
```

- New private helper:

```python
def _run_query(
    G: nx.Graph,
    question: str,
    *,
    mode: str = "bfs",
    depth: int = 3,
    context_filters: list[str] | None = None,
) -> QueryExecution:
```

- `_query_graph_text` calls `_run_query`; it owns only headers and serialization.
- `_query_subgraph_tokens` calls `_run_query`; it contains no independent score loop or BFS.
- Empty `start_nodes` returns empty `nodes` and `edges`, preserving benchmark result `0` and query text `No matching nodes found.`.

- [ ] **Step 1: Add failing benchmark delegation test**

Add to `kb-core/tests/test_benchmark.py`:

```python
from kb_core.serve import QueryExecution


def test_query_subgraph_tokens_uses_production_query_path(monkeypatch):
    G = _make_graph()
    calls = []

    def fake_run_query(graph, question, *, mode="bfs", depth=3, context_filters=None):
        calls.append((graph, question, mode, depth, context_filters))
        return QueryExecution(["n1"], {"n1", "n2"}, [("n1", "n2")], [], "none")

    monkeypatch.setattr("kb_core.benchmark._run_query", fake_run_query)

    result = _query_subgraph_tokens(G, "authentication", depth=1)

    assert result > 0
    assert calls == [(G, "authentication", "bfs", 1, None)]
```

- [ ] **Step 2: Add failing query-text delegation test**

Add to `kb-core/tests/test_serve.py`:

Import `QueryExecution` and `_query_graph_text` using the existing `kb_core.serve` import block.

```python
def test_query_graph_text_uses_shared_query_execution(monkeypatch):
    G = nx.Graph()
    G.add_node("n1", label="authentication", source_file="auth.py", source_location="L1")
    execution = QueryExecution(["n1"], {"n1"}, [], [], "none")
    calls = []

    def fake_run_query(graph, question, *, mode="bfs", depth=3, context_filters=None):
        calls.append((question, mode, depth, context_filters))
        return execution

    monkeypatch.setattr("kb_core.serve._run_query", fake_run_query)

    text = _query_graph_text(G, "authentication", depth=2)

    assert "authentication" in text
    assert calls == [("authentication", "bfs", 2, None)]
```

- [ ] **Step 3: Run focused tests and verify initial failure**

```bash
python -m pytest kb-core/tests/test_benchmark.py::test_query_subgraph_tokens_uses_production_query_path kb-core/tests/test_serve.py::test_query_graph_text_uses_shared_query_execution -q
```

Expected: FAIL because `QueryExecution` and `_run_query` do not exist.

- [ ] **Step 4: Extract shared query execution**

Define `QueryExecution` near existing `NamedTuple` declarations. Move current `_query_graph_text` logic into `_run_query` in this order:

```python
terms = _query_terms(question)
qs = _score_query(G, terms, collect_per_term_seeds=True)
best_seed_by_term = qs.best_seed_by_term
intent = {t for t in best_seed_by_term if t in _RELATIONAL_INTENT_TERMS}
if intent and any(t not in _RELATIONAL_INTENT_TERMS for t in terms):
    best_seed_by_term = {
        t: nid for t, nid in best_seed_by_term.items() if t not in intent
    }
start_nodes = _pick_seeds(qs.ranked, G=G, best_seed_by_term=best_seed_by_term)
if not start_nodes:
    return QueryExecution([], set(), [], [], "none")
resolved_filters, filter_source = _resolve_context_filters(question, context_filters)
traversal_graph = _filter_graph_by_context(G, resolved_filters)
nodes, edges = (
    _dfs(traversal_graph, start_nodes, depth)
    if mode == "dfs"
    else _bfs(traversal_graph, start_nodes, depth)
)
return QueryExecution(start_nodes, nodes, edges, resolved_filters, filter_source)
```

Refactor `_query_graph_text` to use the returned fields. Preserve current headers, graph-path display, context source, seed ordering, and token-budget behavior.

- [ ] **Step 5: Replace benchmark duplicate algorithm**

In `benchmark.py`, import `_run_query` and `_subgraph_to_text` from `kb_core.serve`. Replace manual label scoring and BFS with:

```python
def _query_subgraph_tokens(G: nx.Graph, question: str, depth: int = 3) -> int:
    execution = _run_query(G, question, depth=depth)
    if not execution.start_nodes:
        return 0
    context = _subgraph_to_text(
        G,
        execution.nodes,
        execution.edges,
        token_budget=max(1, len(execution.nodes) * 1000),
        seeds=execution.start_nodes,
    )
    return _estimate_tokens(context)
```

Remove now-unused `edge_data`, `_query_terms`, manual scoring, manual seed selection, and manual traversal. Keep `_estimate_tokens`, `run_benchmark`, and output formatting.

- [ ] **Step 6: Run regression tests**

```bash
python -m pytest kb-core/tests/test_serve.py kb-core/tests/test_benchmark.py -q
```

Expected: existing score, seed, traversal, serialization, and benchmark tests pass with unchanged output keys.

- [ ] **Step 7: Commit**

```bash
git add kb-core/kb_core/serve.py kb-core/kb_core/benchmark.py kb-core/tests/test_serve.py kb-core/tests/test_benchmark.py
git diff --cached --check
git commit -m "Align benchmark with production query path"
```

---

### Task 3: Add Read-Only Runtime Baseline Runner

**Files:**
- Create: `kb-core/tests/bench_runtime.py`
- Test: manual CLI verification; this non-CI benchmark must not become part of the default pytest suite
- Modify: `docs/performance-results.md` only when real before/after measurements exist

**Interfaces:**
- Command:

```bash
python kb-core/tests/bench_runtime.py --graph kb-core-out/graph.json --question "how does authentication work"
```

- Repeated query command:

```bash
python kb-core/tests/bench_runtime.py --graph kb-core-out/graph.json --question "how does authentication work" --repeat 5
```

- JSON output fields: `graph_path`, `nodes`, `edges`, `graph_bytes`, `load_seconds`, `query_seconds`, `query_tokens`, `repeat`, and `rss_bytes`.
- Exit status: `0` valid; `2` missing graph or invalid arguments.
- The script performs no extraction, clustering, export, or graph writes.

- [ ] **Step 1: Implement argument validation**

Use this parser shape:

```python
parser = argparse.ArgumentParser(description="Measure read-only kb-core graph runtime")
parser.add_argument("--graph", required=True)
parser.add_argument("--question", required=True)
parser.add_argument("--repeat", type=int, default=1)
args = parser.parse_args()
if args.repeat < 1:
    parser.error("--repeat must be at least 1")
```

`argparse` supplies exit status `2` for missing or invalid arguments.

- [ ] **Step 2: Measure load and query**

Use this measurement sequence:

```python
graph_path = Path(args.graph).resolve()
if not graph_path.is_file():
    parser.error(f"graph file not found: {graph_path}")

load_started = time.perf_counter()
graph = load_node_link_graph(graph_path)
load_seconds = time.perf_counter() - load_started

query_started = time.perf_counter()
last_context = ""
for _ in range(args.repeat):
    execution = _run_query(graph, args.question)
    last_context = _subgraph_to_text(
        graph,
        execution.nodes,
        execution.edges,
        token_budget=max(1, len(execution.nodes) * 1000),
        seeds=execution.start_nodes,
    ) if execution.start_nodes else ""
query_seconds = (time.perf_counter() - query_started) / args.repeat
```

Read `graph_bytes` with `graph_path.stat().st_size`. Set `query_tokens` with `_estimate_tokens(last_context)` and report node/edge counts from `graph`.

- [ ] **Step 3: Measure RSS portably**

Use this fallback shape:

```python
rss_bytes = None
try:
    import resource
except ImportError:
    resource = None

if resource is not None:
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
else:
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        rss_bytes = psutil.Process().memory_info().rss
```

Serialize the result with `json.dump(..., sys.stdout)` and a trailing newline. Emit `rss_bytes: null` when neither source exists; never fail solely because RSS is unavailable.

- [ ] **Step 4: Run baseline without modifying files**

```bash
python kb-core/tests/bench_runtime.py --graph kb-core-ui/harness/tests/fixtures/go-basics/baseline/graph.json --question "math utility" --repeat 3
git status --short
```

Expected: valid JSON; non-negative timing; matching node/edge counts; no new or modified files from the runner.

- [ ] **Step 5: Record results honestly**

Only after before/after measurements exist, update `docs/performance-results.md` with exact command, commit SHA, graph size, and measured deltas. A single baseline run stays documented as baseline and does not claim improvement.

- [ ] **Step 6: Commit tooling separately**

```bash
git add kb-core/tests/bench_runtime.py
git diff --cached --check
git commit -m "Add read-only graph runtime benchmark"
```

Add `docs/performance-results.md` in this commit only when it contains real before/after data.

---

## Deferred Separate Plans

- Cross-repo identity and deterministic `DEPENDS_ON` edges.
- SQLite-backed `kb-core` query index.
- Score-threshold traversal and intent classification.
- Document `Section`/`Claim` nodes and `DESCRIBES` edges.
- Query/memory bridge and token-category cost persistence.
- Community-level progressive rendering after graph authority is resolved.

## Verification Checklist

- [ ] `python -m pytest kb-core/tests/test_export.py kb-core/tests/test_serve.py kb-core/tests/test_benchmark.py -q` passes.
- [ ] `git diff --cached --check` passes for every commit.
- [ ] `benchmark.py` has no independent label-scoring or BFS implementation.
- [ ] Old graphs without `graph_schema_version` load.
- [ ] New graphs contain `graph_schema_version: 1` and preserve `built_at_commit`.
- [ ] Runtime benchmark performs no graph writes.
- [ ] Generated graph/cache/virtualenv/fixture artifacts remain uncommitted.
