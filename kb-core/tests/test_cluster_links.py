"""Selector resolution and declared cross-repo link materialisation."""
from __future__ import annotations

import pytest

from kb_core.cluster_graph import (
    AmbiguousSelectorError,
    ClusterSpecError,
    apply_auto_package_links,
    apply_spec_links,
    compose_members,
    load_spec,
    resolve_all_members,
)
from tests.cluster_helpers import two_member_cluster, write_member, write_spec


def _compose(tmp_path, **spec_extra):
    cluster_dir = two_member_cluster(tmp_path, **spec_extra)
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))
    return G, spec


def _relations(G, src, tgt):
    if G.is_multigraph():
        return sorted(d.get("relation") for d in G.get_edge_data(src, tgt, default={}).values())
    data = G.get_edge_data(src, tgt)
    return [data["relation"]] if data else []


def test_id_selector_resolves_within_its_member(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib",
    }])
    reports = apply_spec_links(G, spec)

    assert [r.status for r in reports] == ["linked"]
    assert _relations(G, "beta::src_lib", "alpha::src_lib") == ["calls_api"]


def test_label_selector_is_case_insensitive_as_a_fallback(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "references", "from": "beta:label:START()", "to": "alpha:label:parse()",
    }])
    apply_spec_links(G, spec)

    assert _relations(G, "beta::src_lib_start", "alpha::src_lib_parse") == ["references"]


def test_file_selector_picks_the_file_node_not_its_symbols(tmp_path):
    # src/lib.py holds three nodes, two of them at L1 — the file node is the one
    # whose label is the basename.
    G, spec = _compose(tmp_path, links=[{
        "type": "mirrored_file", "from": "alpha:file:src/lib.py", "to": "beta:file:src/lib.py",
    }])
    apply_spec_links(G, spec)

    assert _relations(G, "alpha::src_lib", "beta::src_lib") == ["mirrors"]


def test_file_selector_matches_whole_segments_only(tmp_path):
    write_member(tmp_path, "alpha", nodes=[
        {"id": "a", "label": "prefix_lib.py", "file_type": "code",
         "source_file": "src/prefix_lib.py", "source_location": "L1", "community": 0},
    ], links=[])
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        "links": [{"type": "references", "from": "alpha:file:lib.py",
                   "to": "beta:id:src_lib", "on_missing": "error"}],
    })
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))

    with pytest.raises(ClusterSpecError, match="matches nothing"):
        apply_spec_links(G, spec)


def test_ambiguous_selector_is_an_error(tmp_path):
    write_member(tmp_path, "alpha", nodes=[
        {"id": "one", "label": "dup", "file_type": "code",
         "source_file": "a.py", "source_location": "L1", "community": 0},
        {"id": "two", "label": "dup", "file_type": "code",
         "source_file": "b.py", "source_location": "L1", "community": 0},
    ], links=[])
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        "links": [{"type": "references", "from": "alpha:label:dup", "to": "beta:id:src_lib"}],
    })
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))

    with pytest.raises(AmbiguousSelectorError, match="matches 2 nodes"):
        apply_spec_links(G, spec)


def test_label_selector_falls_back_to_external_nodes(tmp_path):
    write_member(tmp_path, "alpha", nodes=[
        {"id": "ext_redis", "label": "redis", "file_type": "external", "community": 0},
    ], links=[])
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        # auto_link_externals would fuse the two repos' `redis` nodes; keep them
        # separate so this asserts the selector, not the merge.
        "auto_links": {"externals": False},
        "links": [{"type": "references", "from": "beta:id:src_lib",
                   "to": "alpha:label:REDIS", "on_missing": "error"}],
    })
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))
    apply_spec_links(G, spec)

    assert _relations(G, "beta::src_lib", "alpha::ext_redis") == ["references"]


def test_direction_both_materialises_a_real_reverse_edge(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "mirrored_file", "from": "alpha:id:src_lib", "to": "beta:id:src_lib",
        "direction": "both",
    }])
    reports = apply_spec_links(G, spec)

    assert reports[0].edges_added == 2
    assert _relations(G, "alpha::src_lib", "beta::src_lib") == ["mirrors"]
    assert _relations(G, "beta::src_lib", "alpha::src_lib") == ["mirrors"]


def test_shared_resource_creates_a_hub_and_uses_edges(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "shared_resource", "name": "orders", "kind": "queue",
        "referents": ["alpha:id:src_lib", "beta:id:src_lib"],
    }])
    reports = apply_spec_links(G, spec)

    hub = "cluster::queue_orders"
    assert hub in G
    assert G.nodes[hub]["repo"] == "cluster"
    assert G.nodes[hub]["resource_kind"] == "queue"
    assert reports[0].edges_added == 2
    assert _relations(G, "alpha::src_lib", hub) == ["uses"]
    assert _relations(G, "beta::src_lib", hub) == ["uses"]


def test_on_missing_warn_skips_and_reports(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "api_call", "from": "beta:id:ghost", "to": "alpha:id:src_lib",
    }])
    before = G.number_of_edges()
    reports = apply_spec_links(G, spec)

    assert G.number_of_edges() == before
    assert any(r.status == "skipped" for r in reports)


def test_on_missing_create_mints_a_placeholder(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "api_call", "from": "beta:id:src_lib", "to": "alpha:label:notYetExtracted",
        "on_missing": "create",
    }])
    reports = apply_spec_links(G, spec)

    placeholders = [n for n, d in G.nodes(data=True) if d.get("origin") == "cluster_spec"]
    assert len(placeholders) == 1
    assert G.nodes[placeholders[0]]["repo"] == "alpha"
    assert G.nodes[placeholders[0]]["file_type"] == "external"
    assert any(r.status == "created" for r in reports)
    assert _relations(G, "beta::src_lib", placeholders[0]) == ["calls_api"]


def test_on_missing_error_names_the_fix(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "api_call", "from": "beta:id:ghost", "to": "alpha:id:src_lib",
        "on_missing": "error",
    }])
    with pytest.raises(ClusterSpecError, match="kb-core extract"):
        apply_spec_links(G, spec)


def test_link_default_on_missing_comes_from_spec_defaults(tmp_path):
    G, spec = _compose(
        tmp_path,
        defaults={"on_missing": "error"},
        links=[{"type": "api_call", "from": "beta:id:ghost", "to": "alpha:id:src_lib"}],
    )
    with pytest.raises(ClusterSpecError, match="matches nothing"):
        apply_spec_links(G, spec)


def test_self_link_is_skipped(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "references", "from": "alpha:id:src_lib", "to": "alpha:label:lib.py",
    }])
    reports = apply_spec_links(G, spec)

    assert reports[0].status == "skipped"
    assert "both ends resolve to" in reports[0].detail


def test_simple_mode_refuses_a_second_relation_on_one_pair(tmp_path):
    G, spec = _compose(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
        {"type": "references", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    with pytest.raises(ClusterSpecError, match='"graph_mode": "multi"'):
        apply_spec_links(G, spec)


def test_simple_mode_tolerates_a_repeated_identical_relation(tmp_path):
    G, spec = _compose(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    reports = apply_spec_links(G, spec)

    assert [r.edges_added for r in reports] == [1, 0]


def test_multi_mode_keeps_both_relations_on_one_pair(tmp_path):
    G, spec = _compose(tmp_path, graph_mode="multi", links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
        {"type": "references", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    apply_spec_links(G, spec)

    assert _relations(G, "beta::src_lib", "alpha::src_lib") == ["calls_api", "references"]


def test_multi_mode_rejects_a_duplicate_identity(tmp_path):
    G, spec = _compose(tmp_path, graph_mode="multi", links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    with pytest.raises(ClusterSpecError, match="declared twice"):
        apply_spec_links(G, spec)


def test_declared_edges_carry_provenance(tmp_path):
    G, spec = _compose(tmp_path, links=[{
        "type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib",
        "name": "checkout", "note": "beta calls alpha's HTTP API",
    }])
    apply_spec_links(G, spec)
    data = G.get_edge_data("beta::src_lib", "alpha::src_lib")

    assert data["confidence"] == "DECLARED"
    assert data["origin"] == "cluster_spec"
    assert data["cluster_link"] == "api_call"
    assert data["cluster_link_name"] == "checkout"
    assert data["context"] == "beta calls alpha's HTTP API"
    # _src/_tgt survive the graph.json round trip, so direction is recoverable
    # even if the writer canonicalises endpoint order.
    assert (data["_src"], data["_tgt"]) == ("beta::src_lib", "alpha::src_lib")


def _package_member(root, tag, *, key, deps=()):
    write_member(root, tag, nodes=[
        {"id": "pkg", "label": tag, "file_type": "code", "type": "package",
         "source_file": "pyproject.toml", "source_location": "L1", "community": 0,
         "package_key": key, **({"dependency_keys": list(deps)} if deps else {})},
    ], links=[])


def test_auto_package_links_join_consumer_to_provider(tmp_path):
    _package_member(tmp_path, "alpha", key="python:alpha")
    _package_member(tmp_path, "beta", key="python:beta", deps=["python:alpha", "python:requests"])
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        "auto_links": {"packages": True},
    })
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))
    reports = apply_auto_package_links(G)

    assert _relations(G, "beta::pkg", "alpha::pkg") == ["depends_on"]
    assert G.get_edge_data("beta::pkg", "alpha::pkg")["origin"] == "cluster_auto_packages"
    # `python:requests` has no provider in the cluster, so no edge is invented.
    assert reports[0].edges_added == 1


def test_auto_package_links_skip_ambiguous_providers(tmp_path):
    _package_member(tmp_path, "alpha", key="python:shared")
    _package_member(tmp_path, "gamma", key="python:shared")
    _package_member(tmp_path, "beta", key="python:beta", deps=["python:shared"])
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}, {"tag": "gamma"}],
        "auto_links": {"packages": True},
    })
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))

    assert apply_auto_package_links(G) == []
    assert not G.has_edge("beta::pkg", "alpha::pkg")
