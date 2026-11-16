"""Opt-in multigraph mode: parallel edges survive build, save, and reload.

Every test here passes `multigraph=True` explicitly. The default stays a simple
graph, and the assertions that pin that (`test_default_build_stays_simple`,
`test_build_merge_defaults_to_simple_without_a_stored_flag`) are the ones that
guard the ~1100 single-repo tests this feature must not disturb.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from kb_core.build import (
    build_from_json,
    build_merge,
    load_graph_json,
    promote_to_multidigraph,
    stable_edge_key,
)
from kb_core.export import to_json


def _node(node_id: str, line: int = 1) -> dict:
    return {
        "id": node_id,
        "label": f"{node_id}()",
        "file_type": "code",
        "source_file": "src/lib.py",
        "source_location": f"L{line}",
        "_origin": "ast",
    }


def _edge(source: str, target: str, relation: str, line: int) -> dict:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "source_file": "src/lib.py",
        "source_location": f"L{line}",
    }


def _two_calls() -> dict:
    """One caller invoking one callee from two different lines."""
    return {
        "nodes": [_node("caller"), _node("callee", 9)],
        "edges": [
            _edge("caller", "callee", "calls", 3),
            _edge("caller", "callee", "calls", 4),
        ],
    }


# --- build_from_json --------------------------------------------------------


def test_default_build_stays_simple():
    G = build_from_json(_two_calls())

    assert not G.is_multigraph()
    assert G.number_of_edges() == 1


def test_multigraph_keeps_both_call_sites():
    G = build_from_json(_two_calls(), multigraph=True)

    assert isinstance(G, nx.MultiDiGraph)
    assert G.number_of_edges() == 2
    assert sorted(d["source_location"] for _, _, d in G.edges(data=True)) == ["L3", "L4"]


def test_multigraph_implies_directed():
    G = build_from_json(_two_calls(), multigraph=True)

    assert G.is_directed()
    assert G.has_edge("caller", "callee")
    assert not G.has_edge("callee", "caller")


def test_the_same_fact_reported_twice_collapses():
    extraction = {
        "nodes": [_node("caller"), _node("callee", 9)],
        "edges": [_edge("caller", "callee", "calls", 3)] * 2,
    }
    G = build_from_json(extraction, multigraph=True)

    assert G.number_of_edges() == 1


def test_different_relations_between_one_pair_both_survive():
    extraction = {
        "nodes": [_node("caller"), _node("callee", 9)],
        "edges": [
            _edge("caller", "callee", "calls", 3),
            _edge("caller", "callee", "references", 3),
        ],
    }
    G = build_from_json(extraction, multigraph=True)

    assert sorted(k.split(":")[0] for _, _, k in G.edges(keys=True)) == [
        "calls", "references",
    ]


def test_edge_order_does_not_change_the_keys():
    forward = build_from_json(_two_calls(), multigraph=True)
    shuffled = _two_calls()
    shuffled["edges"].reverse()
    reversed_ = build_from_json(shuffled, multigraph=True)

    assert set(forward.edges(keys=True)) == set(reversed_.edges(keys=True))


# --- stable_edge_key --------------------------------------------------------


def test_key_is_derived_from_content_not_position():
    attrs = _edge("caller", "callee", "calls", 3)

    assert stable_edge_key("caller", "callee", attrs) == stable_edge_key(
        "caller", "callee", dict(attrs)
    )
    assert stable_edge_key("caller", "callee", attrs).startswith("calls:")


def test_key_separates_two_call_sites():
    first = stable_edge_key("caller", "callee", _edge("caller", "callee", "calls", 3))
    second = stable_edge_key("caller", "callee", _edge("caller", "callee", "calls", 4))

    assert first != second


def test_key_ignores_attributes_outside_the_edge_identity():
    plain = _edge("caller", "callee", "calls", 3)
    annotated = dict(plain, weight=2.0, note="added later")

    assert stable_edge_key("caller", "callee", plain) == stable_edge_key(
        "caller", "callee", annotated
    )


def test_key_survives_a_process_boundary():
    # A digest seeded by PYTHONHASHSEED would differ between interpreter runs and
    # make every rebuild look like a full edge-set churn.
    import os
    import subprocess
    import sys

    script = (
        "from kb_core.build import stable_edge_key;"
        "print(stable_edge_key('a', 'b', {'relation': 'calls',"
        " 'source_file': 'src/lib.py', 'source_location': 'L3'}))"
    )
    repo = Path(__file__).resolve().parent.parent
    runs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, check=True, cwd=str(repo),
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "1")
    }

    assert len(runs) == 1
    assert runs.pop() == stable_edge_key("a", "b", {
        "relation": "calls", "source_file": "src/lib.py", "source_location": "L3",
    })


# --- promote_to_multidigraph ------------------------------------------------


def test_promotion_keeps_direction_from_the_markers():
    G = nx.Graph()
    G.add_node("callee")
    G.add_node("caller")
    # Endpoint order here is insertion order, not semantics; _src/_tgt hold the truth.
    G.add_edge("callee", "caller", relation="calls", _src="caller", _tgt="callee")
    H = promote_to_multidigraph(G)

    assert H.has_edge("caller", "callee")
    assert not H.has_edge("callee", "caller")


def test_promotion_is_a_no_op_for_a_multidigraph():
    G = nx.MultiDiGraph()
    G.add_edge("a", "b", key="calls:deadbeef", relation="calls")

    assert promote_to_multidigraph(G) is G


# --- graph.json round trip --------------------------------------------------


def test_parallel_edges_survive_save_and_reload(tmp_path):
    G = build_from_json(_two_calls(), multigraph=True)
    out = tmp_path / "graph.json"
    to_json(G, {0: list(G.nodes())}, str(out), force=True)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["multigraph"] is True
    assert payload["directed"] is True

    reloaded = load_graph_json(out, preserve_type=True)
    assert isinstance(reloaded, nx.MultiDiGraph)
    assert reloaded.number_of_edges() == 2
    assert set(reloaded.edges(keys=True)) == set(G.edges(keys=True))


def test_a_simple_graph_json_still_reloads_simple(tmp_path):
    G = build_from_json(_two_calls(), directed=True)
    out = tmp_path / "graph.json"
    to_json(G, {0: list(G.nodes())}, str(out), force=True)

    reloaded = load_graph_json(out, preserve_type=True)
    assert not reloaded.is_multigraph()
    assert reloaded.is_directed()


def test_legacy_edges_key_is_read_as_links(tmp_path):
    out = tmp_path / "graph.json"
    out.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b", "relation": "calls"}],
    }), encoding="utf-8")

    assert load_graph_json(out, preserve_type=True).number_of_edges() == 1


# --- build_merge ------------------------------------------------------------


def _seed(tmp_path: Path, *, multigraph: bool) -> Path:
    graph_path = tmp_path / "kb-core-out" / "graph.json"
    G = build_from_json(_two_calls(), multigraph=multigraph, directed=True)
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    to_json(G, {0: list(G.nodes())}, str(graph_path), force=True)
    return graph_path


def test_build_merge_inherits_the_stored_multigraph_flag(tmp_path):
    graph_path = _seed(tmp_path, multigraph=True)
    merged = build_merge([], graph_path, dedup=False)

    assert merged.is_multigraph()
    assert merged.number_of_edges() == 2


def test_build_merge_defaults_to_simple_without_a_stored_flag(tmp_path):
    graph_path = _seed(tmp_path, multigraph=False)
    merged = build_merge([], graph_path, dedup=False)

    assert not merged.is_multigraph()


def test_build_merge_never_collapses_an_explicit_multigraph(tmp_path):
    graph_path = _seed(tmp_path, multigraph=True)
    chunk = {
        "nodes": [_node("caller"), _node("callee", 9)],
        "edges": [
            _edge("caller", "callee", "calls", 3),
            _edge("caller", "callee", "calls", 4),
            _edge("caller", "callee", "calls", 7),
        ],
    }
    merged = build_merge([chunk], graph_path, dedup=False, multigraph=True)

    assert sorted(d["source_location"] for _, _, d in merged.edges(data=True)) == [
        "L3", "L4", "L7",
    ]


def test_build_merge_can_start_a_multigraph_on_a_fresh_repo(tmp_path):
    graph_path = tmp_path / "kb-core-out" / "graph.json"
    merged = build_merge([_two_calls()], graph_path, dedup=False, multigraph=True)

    assert merged.is_multigraph()
    assert merged.number_of_edges() == 2


# --- community detection ----------------------------------------------------


def test_parallel_edges_aggregate_into_one_weighted_edge(monkeypatch):
    """Two `calls` between a pair is a stronger tie than one, and the partition
    backends read only `weight` — so the parallel edges must sum rather than let
    the last one added win."""
    from kb_core import cluster as clustermod

    seen: dict = {}

    def fake_louvain(graph, **kwargs):
        seen["graph"] = graph
        return [set(graph.nodes())]

    monkeypatch.setattr(
        clustermod.nx.community, "louvain_communities", fake_louvain, raising=True
    )
    G = build_from_json(_two_calls(), multigraph=True)
    clustermod._partition(G)

    stable = seen["graph"]
    assert not stable.is_multigraph()
    assert stable.number_of_edges() == 1
    assert stable.edges["caller", "callee"]["weight"] == 2.0
    assert stable.edges["caller", "callee"]["parallel_count"] == 2


def test_a_simple_graph_partitions_exactly_as_before(monkeypatch):
    from kb_core import cluster as clustermod

    seen: dict = {}

    def fake_louvain(graph, **kwargs):
        seen["graph"] = graph
        return [set(graph.nodes())]

    monkeypatch.setattr(
        clustermod.nx.community, "louvain_communities", fake_louvain, raising=True
    )
    clustermod._partition(build_from_json(_two_calls(), directed=True))

    assert "weight" not in seen["graph"].edges["caller", "callee"]
    assert "parallel_count" not in seen["graph"].edges["caller", "callee"]
