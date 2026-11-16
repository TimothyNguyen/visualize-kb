"""Cluster spec schema: load, save, and every validation error path."""
from __future__ import annotations

import json

import pytest

from kb_core.cluster_graph import (
    ClusterLink,
    ClusterMember,
    ClusterSpec,
    ClusterSpecError,
    find_spec_file,
    load_local_config,
    load_spec,
    save_local_config,
    save_spec,
    spec_to_dict,
    validate_member_tag,
)
from tests.cluster_helpers import write_spec


def _spec(**over) -> dict:
    payload = {"schema_version": 1, "name": "demo", "members": [{"tag": "alpha"}]}
    payload.update(over)
    return payload


def test_round_trips_through_save_and_load(tmp_path):
    spec = ClusterSpec(
        name="demo",
        members=[ClusterMember(tag="alpha", url="https://github.com/o/alpha.git")],
        links=[ClusterLink(
            type="api_call",
            from_={"member": "alpha", "kind": "label", "value": "call()"},
            to={"member": "alpha", "kind": "id", "value": "src_lib"},
            direction="both",
            note="why",
        )],
        graph_mode="multi",
        auto_link_packages=True,
        search_roots=["../repos"],
    )
    save_spec(tmp_path, spec)
    reloaded = load_spec(tmp_path)

    assert spec_to_dict(reloaded) == spec_to_dict(spec)
    assert reloaded.graph_mode == "multi"
    assert reloaded.auto_link_packages is True
    assert reloaded.links[0].direction == "both"
    assert reloaded.search_roots == ["../repos"]


def test_defaults_when_optional_keys_absent(tmp_path):
    write_spec(tmp_path, _spec())
    spec = load_spec(tmp_path)

    assert spec.graph_mode == "simple"
    assert spec.default_on_missing == "warn"
    assert spec.auto_link_externals is True
    assert spec.auto_link_packages is False
    assert spec.members[0].graph == "kb-core-out/graph.json"


def test_compact_selector_keeps_colons_in_the_value(tmp_path):
    write_spec(tmp_path, _spec(links=[{
        "type": "references",
        "from": "alpha:label:mod::helper",
        "to": "alpha:file:C:/win/path.py",
    }]))
    link = load_spec(tmp_path).links[0]

    assert link.from_ == {"member": "alpha", "kind": "label", "value": "mod::helper"}
    assert link.to == {"member": "alpha", "kind": "file", "value": "C:/win/path.py"}


def test_missing_spec_names_the_fix(tmp_path):
    with pytest.raises(ClusterSpecError, match="cluster init"):
        load_spec(tmp_path)


def test_find_spec_file_prefers_json(tmp_path):
    (tmp_path / "cluster.yaml").write_text("name: y", encoding="utf-8")
    write_spec(tmp_path, _spec())
    assert find_spec_file(tmp_path).name == "cluster.json"


@pytest.mark.parametrize("tag", ["", "   ", None, 42])
def test_rejects_empty_or_non_string_tag(tag):
    with pytest.raises(ClusterSpecError, match="non-empty string 'tag'"):
        validate_member_tag(tag)


def test_rejects_reserved_tag():
    with pytest.raises(ClusterSpecError, match="reserved"):
        validate_member_tag("cluster")


def test_rejects_tag_containing_the_id_separator():
    with pytest.raises(ClusterSpecError, match="'::'"):
        validate_member_tag("a::b")


@pytest.mark.parametrize("tag", ["a/b", "a\\b"])
def test_rejects_tag_with_path_separator(tag):
    with pytest.raises(ClusterSpecError, match="path separator"):
        validate_member_tag(tag)


def test_rejects_duplicate_tags(tmp_path):
    write_spec(tmp_path, _spec(members=[{"tag": "alpha"}, {"tag": "alpha"}]))
    with pytest.raises(ClusterSpecError, match="duplicate member tag"):
        load_spec(tmp_path)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"schema_version": 99, "name": "d"}, "schema_version"),
        ({"name": ""}, "non-empty string 'name'"),
        ({"name": "d", "members": {}}, "'members' must be a list"),
        ({"name": "d", "members": ["alpha"]}, "must be an object"),
        ({"name": "d", "links": {}}, "'links' must be a list"),
        ({"name": "d", "defaults": []}, "'defaults' must be an object"),
        ({"name": "d", "defaults": {"on_missing": "nope"}}, "defaults.on_missing"),
        ({"name": "d", "auto_links": []}, "'auto_links' must be an object"),
        ({"name": "d", "graph_mode": "hyper"}, "graph_mode must be one of"),
        ({"name": "d", "search_roots": "x"}, "'search_roots' must be a list"),
    ],
)
def test_top_level_validation_errors(tmp_path, payload, match):
    write_spec(tmp_path, payload)
    with pytest.raises(ClusterSpecError, match=match):
        load_spec(tmp_path)


@pytest.mark.parametrize(
    ("link", "match"),
    [
        ("not-an-object", "must be an object"),
        ({"type": "teleports"}, "unknown link type"),
        ({"type": "api_call", "from": "alpha:id:x"}, "needs both 'from' and 'to'"),
        ({"type": "api_call", "from": "alpha:id:x", "to": "alpha:id:y",
          "on_missing": "explode"}, "on_missing must be one of"),
        ({"type": "api_call", "from": "alpha:id:x", "to": "alpha:id:y",
          "direction": "sideways"}, "direction must be one of"),
        ({"type": "shared_resource", "referents": [{"member": "alpha", "id": "x"}]},
         "needs a 'name'"),
        ({"type": "shared_resource", "name": "q", "referents": []},
         "non-empty 'referents' list"),
        ({"type": "api_call", "from": "alpha:id", "to": "alpha:id:y"},
         "MEMBER:KIND:VALUE"),
        ({"type": "api_call", "from": {"id": "x"}, "to": "alpha:id:y"},
         "needs a 'member' tag"),
        ({"type": "api_call", "from": {"member": "alpha"}, "to": "alpha:id:y"},
         "needs exactly one of"),
        ({"type": "api_call", "from": {"member": "alpha", "id": "x", "label": "y"},
          "to": "alpha:id:y"}, "needs exactly one of"),
        ({"type": "api_call", "from": "ghost:id:x", "to": "alpha:id:y"},
         "not in this cluster"),
    ],
)
def test_link_validation_errors(tmp_path, link, match):
    write_spec(tmp_path, _spec(links=[link]))
    with pytest.raises(ClusterSpecError, match=match):
        load_spec(tmp_path)


def test_malformed_json_reports_the_file(tmp_path):
    (tmp_path / "cluster.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(ClusterSpecError, match="cluster.json is not valid JSON"):
        load_spec(tmp_path)


def test_non_object_top_level_rejected(tmp_path):
    (tmp_path / "cluster.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ClusterSpecError, match="object at the top level"):
        load_spec(tmp_path)


def test_local_config_is_fail_open(tmp_path):
    (tmp_path / "cluster.local.json").write_text("{not json", encoding="utf-8")
    assert load_local_config(tmp_path) == {"paths": {}}

    (tmp_path / "cluster.local.json").write_text('{"paths": []}', encoding="utf-8")
    assert load_local_config(tmp_path) == {"paths": {}}


def test_local_config_round_trip(tmp_path):
    save_local_config(tmp_path, {"paths": {"alpha": "../alpha"}, "junk": 1})
    payload = json.loads((tmp_path / "cluster.local.json").read_text(encoding="utf-8"))

    assert payload == {"paths": {"alpha": "../alpha"}}
    assert load_local_config(tmp_path)["paths"]["alpha"] == "../alpha"


def test_save_spec_keeps_a_yaml_spec_as_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    (tmp_path / "cluster.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "name": "demo", "members": [{"tag": "alpha"}]}),
        encoding="utf-8",
    )
    spec = load_spec(tmp_path)
    spec.members.append(ClusterMember(tag="beta"))
    path = save_spec(tmp_path, spec)

    assert path.name == "cluster.yaml"
    assert not (tmp_path / "cluster.json").exists()
    assert load_spec(tmp_path).tags == ["alpha", "beta"]
