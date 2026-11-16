"""End-to-end cluster composition: build_cluster and its invariants."""
from __future__ import annotations

import json

import pytest

from kb_core.cluster_graph import (
    ClusterSpecError,
    build_cluster,
    check_cluster,
    compose_members,
    load_spec,
    resolve_all_members,
    save_local_config,
)
from tests.cluster_helpers import two_member_cluster, write_member, write_spec


def _graph(cluster_dir):
    return json.loads((cluster_dir / "kb-core-out" / "graph.json").read_text(encoding="utf-8"))


def test_build_writes_graph_manifest_report_and_markers(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    result = build_cluster(cluster_dir)

    out = cluster_dir / "kb-core-out"
    assert (out / "graph.json").is_file()
    assert (out / "cluster-manifest.json").is_file()
    assert (out / "CLUSTER_REPORT.md").is_file()
    assert result["members"] == 2
    assert result["nodes"] == 6

    manifest = json.loads((out / "cluster-manifest.json").read_text(encoding="utf-8"))
    assert [m["tag"] for m in manifest["members"]] == ["alpha", "beta"]
    assert manifest["graph_mode"] == "simple"

    for tag in ("alpha", "beta"):
        marker = tmp_path / tag / "kb-core-out" / "cluster-ref.json"
        assert marker.is_file()
        payload = json.loads(marker.read_text(encoding="utf-8"))
        assert payload["clusters"][0]["cluster_name"] == "demo"
        assert payload["clusters"][0]["self_tag"] == tag


def test_nodes_are_namespaced_by_tag(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    build_cluster(cluster_dir)
    ids = {n["id"] for n in _graph(cluster_dir)["nodes"]}

    assert "alpha::src_lib" in ids
    assert "beta::src_lib" in ids


def test_composition_preserves_edge_direction(tmp_path):
    # The regression this guards: an undirected intermediate canonicalises
    # endpoint order by node insertion, silently reversing caller -> callee.
    cluster_dir = two_member_cluster(tmp_path)
    spec = load_spec(cluster_dir)
    G, _ = compose_members(spec, resolve_all_members(spec, cluster_dir))

    assert G.is_directed()
    assert G.has_edge("alpha::src_lib_start", "alpha::src_lib_parse")
    assert not G.has_edge("alpha::src_lib_parse", "alpha::src_lib_start")


def test_direction_survives_the_graph_json_round_trip(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    build_cluster(cluster_dir)
    links = _graph(cluster_dir)["links"]
    call = next(l for l in links
                if l.get("relation") == "calls" and "alpha" in str(l.get("_src", l["source"])))

    assert (call.get("_src") or call["source"]) == "alpha::src_lib_start"
    assert (call.get("_tgt") or call["target"]) == "alpha::src_lib_parse"


def test_member_order_does_not_change_the_result(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    build_cluster(cluster_dir)
    first = (cluster_dir / "kb-core-out" / "graph.json").read_bytes()

    spec_path = cluster_dir / "cluster.json"
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["members"].reverse()
    spec_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    build_cluster(cluster_dir, force=True)

    assert (cluster_dir / "kb-core-out" / "graph.json").read_bytes() == first


def test_rebuild_is_byte_stable(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    build_cluster(cluster_dir)
    first = (cluster_dir / "kb-core-out" / "graph.json").read_bytes()
    build_cluster(cluster_dir, force=True)

    assert (cluster_dir / "kb-core-out" / "graph.json").read_bytes() == first


def test_community_ids_are_renumbered_into_disjoint_ranges(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    spec = load_spec(cluster_dir)
    G, stats = compose_members(spec, resolve_all_members(spec, cluster_dir))

    by_repo: dict[str, set[int]] = {}
    for _, data in G.nodes(data=True):
        by_repo.setdefault(data["repo"], set()).add(data["community"])

    assert by_repo["alpha"] == {0, 1}
    assert by_repo["beta"] == {2, 3}
    assert [s.community_offset for s in stats] == [0, 2]


def test_shared_type_declarations_are_linked(tmp_path):
    typed = [
        {"id": "order", "label": "Order", "file_type": "code", "type": "class",
         "_callable_class": True, "metadata": {"namespace": "Contracts.Models"},
         "source_file": "src/models.py", "source_location": "L1", "community": 0},
    ]
    write_member(tmp_path, "alpha", nodes=typed, links=[])
    write_member(tmp_path, "beta", nodes=typed, links=[])
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        "auto_links": {"externals": False},
    })
    result = build_cluster(cluster_dir)

    assert result["shared_type_edges"] >= 1
    relations = {l.get("relation") for l in _graph(cluster_dir)["links"]}
    assert "same_type_as" in relations


def test_multi_mode_graph_round_trips_as_a_multigraph(tmp_path):
    cluster_dir = two_member_cluster(tmp_path, graph_mode="multi", links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
        {"type": "references", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    result = build_cluster(cluster_dir)
    payload = _graph(cluster_dir)

    assert payload["multigraph"] is True
    assert payload["directed"] is True
    assert result["edges"] == 6
    parallel = [
        l for l in payload["links"]
        if {l.get("_src", l["source"]), l.get("_tgt", l["target"])}
        == {"beta::src_lib", "alpha::src_lib"}
    ]
    assert sorted(l["relation"] for l in parallel) == ["calls_api", "references"]


def test_no_links_flag_skips_declared_links(tmp_path):
    cluster_dir = two_member_cluster(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    result = build_cluster(cluster_dir, no_links=True)

    assert result["links"] == []
    relations = {l.get("relation") for l in _graph(cluster_dir)["links"]}
    assert "calls_api" not in relations


def test_no_refs_flag_leaves_members_unmarked(tmp_path):
    cluster_dir = two_member_cluster(tmp_path)
    result = build_cluster(cluster_dir, write_refs=False)

    assert result["refs_written"] == []
    assert not (tmp_path / "alpha" / "kb-core-out" / "cluster-ref.json").exists()


def test_local_config_overrides_member_location(tmp_path):
    write_member(tmp_path / "elsewhere", "alpha")
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
    })
    save_local_config(cluster_dir, {"paths": {"alpha": "../elsewhere/alpha"}})
    spec = load_spec(cluster_dir)
    resolved = resolve_all_members(spec, cluster_dir)

    assert resolved["alpha"] == (tmp_path / "elsewhere" / "alpha")


def test_member_resolved_by_origin_url(tmp_path):
    write_member(tmp_path, "renamed-on-disk", origin="git@github.com:org/alpha.git")
    write_member(tmp_path, "beta")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [
            {"tag": "alpha", "url": "https://github.com/org/alpha"},
            {"tag": "beta"},
        ],
    })
    spec = load_spec(cluster_dir)
    resolved = resolve_all_members(spec, cluster_dir)

    assert resolved["alpha"].name == "renamed-on-disk"


def test_empty_cluster_names_the_fix(tmp_path):
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {"schema_version": 1, "name": "demo", "members": []})
    with pytest.raises(ClusterSpecError, match="cluster add"):
        check_cluster(cluster_dir)


def test_unresolvable_member_names_the_fix(tmp_path):
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo", "members": [{"tag": "ghost"}],
    })
    with pytest.raises(ClusterSpecError, match="cluster locate ghost"):
        check_cluster(cluster_dir)


def test_member_without_a_graph_names_the_fix(tmp_path):
    write_member(tmp_path, "alpha")
    (tmp_path / "alpha" / "kb-core-out" / "graph.json").unlink()
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo", "members": [{"tag": "alpha"}],
    })
    with pytest.raises(ClusterSpecError, match="kb-core extract"):
        check_cluster(cluster_dir)


def test_corrupt_member_graph_names_the_member(tmp_path):
    write_member(tmp_path, "alpha")
    (tmp_path / "alpha" / "kb-core-out" / "graph.json").write_text("{oops", encoding="utf-8")
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo", "members": [{"tag": "alpha"}],
    })
    spec = load_spec(cluster_dir)
    resolved = resolve_all_members(spec, cluster_dir)
    with pytest.raises(ClusterSpecError, match="could not be read"):
        compose_members(spec, resolved)


def test_cluster_cannot_contain_itself(tmp_path):
    cluster_dir = tmp_path / "cluster"
    write_member(cluster_dir.parent, "cluster")
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo", "members": [{"tag": "cluster-self"}],
    })
    save_local_config(cluster_dir, {"paths": {"cluster-self": "."}})
    with pytest.raises(ClusterSpecError, match="cannot contain itself"):
        check_cluster(cluster_dir)


def test_two_clusters_sharing_a_name_are_refused(tmp_path):
    write_member(tmp_path, "alpha")
    write_member(tmp_path, "beta")
    for holder in ("one", "two"):
        write_spec(tmp_path / holder, {
            "schema_version": 1, "name": "demo",
            "members": [{"tag": "alpha"}, {"tag": "beta"}],
        })
        save_local_config(tmp_path / holder, {
            "paths": {"alpha": "../alpha", "beta": "../beta"},
        })
    build_cluster(tmp_path / "one")

    with pytest.raises(ClusterSpecError, match="Rename one of them"):
        build_cluster(tmp_path / "two")


def test_a_repo_can_belong_to_two_differently_named_clusters(tmp_path):
    write_member(tmp_path, "alpha")
    write_member(tmp_path, "beta")
    for holder, name in (("one", "left"), ("two", "right")):
        write_spec(tmp_path / holder, {
            "schema_version": 1, "name": name,
            "members": [{"tag": "alpha"}, {"tag": "beta"}],
        })
        save_local_config(tmp_path / holder, {
            "paths": {"alpha": "../alpha", "beta": "../beta"},
        })
        build_cluster(tmp_path / holder)

    payload = json.loads(
        (tmp_path / "alpha" / "kb-core-out" / "cluster-ref.json").read_text(encoding="utf-8")
    )
    assert [c["cluster_name"] for c in payload["clusters"]] == ["left", "right"]
