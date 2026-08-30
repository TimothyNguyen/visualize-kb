#!/usr/bin/env python3
"""Read-only runtime baseline for kb-core graph load and query latency."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure the project root is importable when run as a script.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from kb_core.benchmark import _estimate_tokens
from kb_core.paths import load_node_link_graph
from kb_core.security import check_graph_file_size_cap
from kb_core.serve import _run_query, _subgraph_to_text

try:
    import resource
except ImportError:
    resource = None


def _measure_rss_bytes() -> int | None:
    if resource is not None:
        maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(maxrss if sys.platform == "darwin" else maxrss * 1024)
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        return psutil.Process().memory_info().rss
    return None


def _is_node_link_graph_payload(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("nodes"), list):
        return False
    return isinstance(data.get("links"), list) or isinstance(data.get("edges"), list)


def _load_benchmark_graph(parser: argparse.ArgumentParser, graph_path: Path):
    try:
        check_graph_file_size_cap(graph_path)
    except ValueError as exc:
        parser.error(f"incompatible graph input: {graph_path} ({exc})")

    try:
        file_data = json.loads(graph_path.read_text(encoding="utf-8"))
    except OSError as exc:
        parser.error(f"cannot read graph file: {graph_path} ({exc})")
    except UnicodeError as exc:
        parser.error(f"invalid graph encoding: {graph_path} ({exc})")
    except json.JSONDecodeError as exc:
        parser.error(f"invalid graph JSON: {graph_path} ({exc})")
    if not isinstance(file_data, dict):
        parser.error(f"incompatible graph input: {graph_path} (top-level JSON must be an object)")

    comparable = file_data.get("comparable")
    body = comparable.get("body") if isinstance(comparable, dict) else None
    graph_input = body if _is_node_link_graph_payload(body) else file_data

    try:
        return load_node_link_graph(graph_input)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(f"incompatible graph input: {graph_path} ({exc})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure read-only kb-core graph runtime"
    )
    parser.add_argument("--graph", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    graph_path = Path(args.graph).resolve()
    if not graph_path.is_file():
        parser.error(f"graph file not found: {graph_path}")

    load_started = time.perf_counter()
    graph = _load_benchmark_graph(parser, graph_path)
    load_seconds = time.perf_counter() - load_started

    query_started = time.perf_counter()
    last_context = ""
    for _ in range(args.repeat):
        execution = _run_query(graph, args.question)
        traversal_graph = getattr(execution, "traversal_graph", None)
        if traversal_graph is None:
            traversal_graph = graph
        last_context = (
            _subgraph_to_text(
                traversal_graph,
                execution.nodes,
                execution.edges,
                token_budget=max(1, len(execution.nodes) * 1000),
                seeds=execution.start_nodes,
            )
            if execution.start_nodes
            else ""
        )
    query_seconds = (time.perf_counter() - query_started) / args.repeat

    result = {
        "graph_path": str(graph_path),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "graph_bytes": graph_path.stat().st_size,
        "load_seconds": load_seconds,
        "query_seconds": query_seconds,
        "query_tokens": _estimate_tokens(last_context),
        "repeat": args.repeat,
        "rss_bytes": _measure_rss_bytes(),
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
