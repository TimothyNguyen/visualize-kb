"""Member-side cluster markers: cluster-ref.json read/write/resolve."""
from __future__ import annotations

import json

import pytest

from kb_core.cluster_ref import (
    CLUSTER_REF_VERSION,
    build_ref_entry,
    cluster_hint_line,
    load_cluster_refs,
    member_count,
    normalize_git_url,
    origin_url,
    ref_path,
    remove_cluster_ref,
    resolve_cluster_dir,
    select_cluster_ref,
    unresolvable_message,
    upsert_cluster_ref,
)
from tests.cluster_helpers import write_member, write_spec


@pytest.mark.parametrize("url", [
    "git@github.com:Org/Repo.git",
    "https://github.com/org/repo.git",
    "https://github.com/org/repo/",
    "ssh://git@github.com/org/repo",
    "git+https://github.com/org/repo.git",
    "http://github.com/org/repo",
])
def test_every_spelling_of_one_remote_compares_equal(url):
    assert normalize_git_url(url) == "github.com/org/repo"


def test_normalize_passes_through_non_urls():
    assert normalize_git_url("") == ""
    assert normalize_git_url(None) == ""
    assert normalize_git_url("../sibling") == "../sibling"


def test_origin_url_parses_git_config(tmp_path):
    repo = write_member(tmp_path, "alpha", origin="git@github.com:org/alpha.git")
    assert origin_url(repo) == "git@github.com:org/alpha.git"


def test_origin_url_is_empty_without_a_remote(tmp_path):
    assert origin_url(write_member(tmp_path, "alpha")) == ""
    assert origin_url(tmp_path / "nope") == ""


def _entry(tmp_path, name="demo", tag="alpha"):
    return build_ref_entry(
        cluster_name=name,
        cluster_dir=tmp_path / "cluster",
        member_root=tmp_path / tag,
        self_tag=tag,
        members=[{"tag": "alpha", "url": ""}, {"tag": "beta", "url": ""}],
        built_at="2026-01-01T00:00:00+00:00",
    )


def test_entry_records_a_relative_dir_hint(tmp_path):
    entry = _entry(tmp_path)
    assert entry["dir_hint"] == "../cluster"
    assert entry["member_count"] == 2


def test_upsert_replaces_by_name_and_accumulates_others(tmp_path):
    out = tmp_path / "alpha" / "kb-core-out"
    upsert_cluster_ref(out, _entry(tmp_path, name="left"))
    upsert_cluster_ref(out, _entry(tmp_path, name="right"))
    upsert_cluster_ref(out, dict(_entry(tmp_path, name="left"), self_tag="renamed"))

    refs = load_cluster_refs(out)
    assert [r["cluster_name"] for r in refs] == ["left", "right"]
    assert next(r for r in refs if r["cluster_name"] == "left")["self_tag"] == "renamed"


def test_remove_drops_one_cluster_and_deletes_an_emptied_marker(tmp_path):
    out = tmp_path / "alpha" / "kb-core-out"
    upsert_cluster_ref(out, _entry(tmp_path, name="left"))
    upsert_cluster_ref(out, _entry(tmp_path, name="right"))

    assert remove_cluster_ref(out, "left") is True
    assert [r["cluster_name"] for r in load_cluster_refs(out)] == ["right"]
    assert remove_cluster_ref(out, "missing") is False

    assert remove_cluster_ref(out, "right") is True
    assert not ref_path(out).exists()
    assert load_cluster_refs(out) == []


@pytest.mark.parametrize("body", [
    "{not json",
    '{"version": 99, "clusters": []}',
    '{"clusters": "nope", "version": 1}',
    '[1, 2, 3]',
])
def test_reads_fail_open(tmp_path, body):
    out = tmp_path / "kb-core-out"
    out.mkdir(parents=True)
    ref_path(out).write_text(body, encoding="utf-8")
    assert load_cluster_refs(out) == []


def test_duplicate_cluster_names_read_as_no_clusters(tmp_path):
    # Two entries claiming one name means `--cluster NAME` has no single answer;
    # reporting none is better than picking arbitrarily.
    out = tmp_path / "kb-core-out"
    out.mkdir(parents=True)
    ref_path(out).write_text(json.dumps({
        "version": CLUSTER_REF_VERSION,
        "clusters": [{"cluster_name": "demo"}, {"cluster_name": "demo"}],
    }), encoding="utf-8")

    assert load_cluster_refs(out) == []


def test_oversized_marker_is_ignored(tmp_path):
    out = tmp_path / "kb-core-out"
    out.mkdir(parents=True)
    ref_path(out).write_text(
        json.dumps({"version": CLUSTER_REF_VERSION, "clusters": [{"cluster_name": "demo"}],
                    "pad": "x" * (1024 * 1024 + 10)}),
        encoding="utf-8",
    )
    assert load_cluster_refs(out) == []


def test_missing_marker_reads_as_no_clusters(tmp_path):
    assert load_cluster_refs(tmp_path / "nothing-here") == []


def test_select_requires_a_name_when_several_clusters_exist():
    refs = [{"cluster_name": "left"}, {"cluster_name": "right"}]

    assert select_cluster_ref(refs) is None
    assert select_cluster_ref(refs, "right")["cluster_name"] == "right"
    assert select_cluster_ref(refs, "absent") is None
    assert select_cluster_ref([{"cluster_name": "only"}])["cluster_name"] == "only"
    assert select_cluster_ref([]) is None


def test_member_count_prefers_the_member_list():
    assert member_count({"members": [{"tag": "a"}], "member_count": 9}) == 1
    assert member_count({"member_count": 3}) == 3
    assert member_count({"member_count": "junk"}) == 0
    assert member_count({}) == 0


def test_hint_line_scales_with_cluster_count():
    assert cluster_hint_line([]) == ""
    one = cluster_hint_line([{"cluster_name": "demo", "member_count": 2}])
    assert "'demo' (2 repos)" in one and "--cluster" in one

    many = cluster_hint_line([{"cluster_name": "left"}, {"cluster_name": "right"}])
    assert "2 clusters (left, right)" in many
    assert "--cluster <NAME>" in many


def test_unresolvable_message_quotes_the_last_known_location():
    text = unresolvable_message({"cluster_name": "demo", "dir_hint": "../cluster"})
    assert "demo" in text and "../cluster" in text and "--graph" in text


def _cluster_at(tmp_path, where, name="demo", origin=""):
    write_spec(tmp_path / where, {"schema_version": 1, "name": name, "members": []})
    if origin:
        git = tmp_path / where / ".git"
        git.mkdir(exist_ok=True)
        (git / "config").write_text(f'[remote "origin"]\n\turl = {origin}\n', encoding="utf-8")
    return tmp_path / where


def test_resolves_through_the_dir_hint(tmp_path):
    _cluster_at(tmp_path, "cluster")
    member = write_member(tmp_path, "alpha")
    assert resolve_cluster_dir(_entry(tmp_path), member) == tmp_path / "cluster"


def test_stale_dir_hint_falls_back_to_sibling_discovery(tmp_path):
    _cluster_at(tmp_path, "moved-cluster")
    member = write_member(tmp_path, "alpha")
    entry = dict(_entry(tmp_path), dir_hint="../gone")

    # Nothing at the hint, but exactly one sibling declares the cluster name.
    assert resolve_cluster_dir(entry, member) == tmp_path / "moved-cluster"


def test_sibling_discovery_matches_on_origin_url(tmp_path):
    _cluster_at(tmp_path, "renamed", name="other-name",
                origin="git@github.com:org/cluster.git")
    member = write_member(tmp_path, "alpha")
    entry = dict(
        _entry(tmp_path),
        dir_hint="../gone",
        cluster_url="https://github.com/org/cluster",
    )

    assert resolve_cluster_dir(entry, member) == tmp_path / "renamed"


def test_two_candidate_clusters_resolve_to_nothing(tmp_path):
    # Guessing between them would give a silently wrong answer, so the caller
    # gets the explicit "pass --graph" path instead.
    _cluster_at(tmp_path, "demo")
    _cluster_at(tmp_path, "also-demo", name="demo")
    member = write_member(tmp_path, "alpha")

    assert resolve_cluster_dir(dict(_entry(tmp_path), dir_hint="../gone"), member) is None


def test_a_directory_without_a_spec_is_not_a_cluster(tmp_path):
    (tmp_path / "cluster").mkdir()
    member = write_member(tmp_path, "alpha")

    assert resolve_cluster_dir(_entry(tmp_path), member) is None
