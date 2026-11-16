# Performance Baseline — Methodology

**This document is methodology only. No numbers are recorded here yet.** Numbers get filled into `performance-results.md` once a migration-plan stage is implemented and benchmarked (see `migration-plan.md`).

## 1. What already exists

`kb-core` ships one benchmark: **token-reduction only**.

- Implementation: `kb_core/benchmark.py` — `run_benchmark(graph_path, corpus_words, questions)` (lines 85-133, verified) and `print_benchmark()` (lines 136-152, verified).
- What it measures: estimates naive-corpus tokens (`corpus_words * 100 // 75`, a words→tokens approximation) vs. average tokens needed to answer 5 sample questions (`_SAMPLE_QUESTIONS`, `benchmark.py:76-82`) via a **from-scratch, simplified** BFS (`_query_subgraph_tokens`, `benchmark.py:37-73`) that scores nodes by literal substring match against query terms and starts from the top 3 — it does **not** call `serve.py`'s real query path (`_score_query`/`_pick_seeds`/`_bfs`); see `query-engine-design.md` for the duplicate-responsibility note.
- CLI wiring: `cli.py:2913-2928` (verified) — `elif cmd == "benchmark":` loads the graph (default path via `_default_graph_path()` or `sys.argv[2]`), enforces `_enforce_graph_size_cap_or_exit`, opportunistically reads `corpus_words` from `.kb_core_detect.json`'s `total_words` field, then calls `run_benchmark` + `print_benchmark`.
- Entry point: `pyproject.toml:100` → `kb-core = "kb_core.__main__:main"`.
- **Runnable command today**: `kb-core benchmark [path/to/graph.json]` (or `python -m kb_core benchmark ...` if not installed as a console script).
- Output: `corpus_tokens`, `corpus_words`, `nodes`, `edges`, `avg_query_tokens`, `reduction_ratio`, `per_question` (list of `{question, query_tokens, reduction}`).

**Not measured by anything in `kb_core/` today**: wall-clock latency, CPU time, peak RSS, bytes on disk (cache size, `graph.json` size), disk read/write bytes, nodes/edges processed per second during build, LLM `$` cost per query (see `token-cost-analysis.md`), browser render latency/FPS (see `graph-rendering-analysis.md`).

A separate, heavier suite exists in `BENCHMARKS.md` (`memory/runner.py`, `crosstool/run.py`) targeting external long-context datasets (LOCOMO, LongMemEval) with real API spend — **out of scope for this local dev-loop baseline**; don't conflate it with `kb_core/benchmark.py`.

## 2. Graph size tiers

No existing size-tier convention was found in `kb-core/tests/test_benchmark.py` or `test_benchmark_raw_graph.py`. Define fresh:

| Tier | Nodes (approx) |
|---|---|
| small | ~1,000 |
| medium | ~10,000 |
| large | ~50,000 |
| xlarge | ~100,000 |
| stress | 250,000+ (only if a corpus of that size is available; else synthetic) |

Fixtures: prefer real repositories already present under the workspace for small/medium; synthesize (script-generated NetworkX graphs matching kb-core's node/edge schema) for large/xlarge/stress where no real corpus of that size exists, so the benchmark is reproducible without depending on finding an enormous real repo.

## 3. Procedure

For each tier:
1. Build (or synthesize) the graph, capturing `kb-core extract` wall-clock time and peak RSS externally (the extractor itself doesn't self-report these — wrap the process, e.g. `/usr/bin/time -v` on Linux or `Measure-Command`/working-set sampling on Windows).
2. Run `kb-core benchmark <graph.json>` for the existing token-reduction numbers.
3. Record `graph.json` file size on disk and cache directory size (`cache/ast/`, `cache/semantic/`) as write-amplification signals.
4. Repeat for a 1-file, 10-file, and 100-file incremental update (touch N files, rerun `kb-core extract` in incremental mode, time it) to characterize `detect_incremental`'s actual scaling (see `architecture-current.md` §5.2 — discovery still full-corpus-scans even though extraction is incremental).
5. On the kb-core-ui side: time `store.py` reindex, REST `/graph/subgraph` response latency, and frontend render time via browser devtools (Performance tab) for the graph sizes that load in the UI.

## 4. Metrics table

| Metric | Status |
|---|---|
| Token reduction ratio | Existing (`benchmark.py`) |
| Wall-clock latency (index, incremental, query) | Needs instrumentation (external timing wrapper) |
| CPU time | Needs instrumentation |
| Peak RSS | Needs instrumentation |
| `graph.json` / cache bytes on disk | Needs instrumentation (simple `os.path.getsize` / `du`) |
| Nodes/edges processed per second | Needs instrumentation |
| LLM $ cost per query | Partially existing — `estimate_cost()` exists (`llm.py:3021`) but only wired into `extract`'s stdout print (`cli.py:4266-4288`), not into query-time cost tracking; see `token-cost-analysis.md` |
| Browser render latency / FPS | Needs instrumentation (browser Performance API) |
| Search latency in UI | Needs instrumentation |

## 5. Reporting template (for `performance-results.md`, deferred)

```
### <Stage N> — <what changed>
Before: <metric> = <value>  (measured <date>, commit <sha>)
After:  <metric> = <value>  (measured <date>, commit <sha>)
Delta:  <±%>
Method: <exact command(s) run>
```
