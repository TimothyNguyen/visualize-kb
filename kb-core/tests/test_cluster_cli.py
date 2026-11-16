"""`kb-core cluster ...` subcommands and `--cluster` on the read-only commands."""
from __future__ import annotations

import json

import pytest

import kb_core.__main__ as mainmod
from kb_core.cluster_graph import build_cluster, load_local_config, load_spec
from tests.cluster_helpers import two_member_cluster, write_member, write_spec


def run(monkeypatch, capsys, *argv, cwd=None):
    """Invoke the CLI the way a shell would; returns (exit_code, stdout, stderr)."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["kb-core", *argv])
    if cwd is not None:
        monkeypatch.chdir(cwd)
    code = 0
    try:
        mainmod.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    out = capsys.readouterr()
    return code, out.out, out.err


# --- cluster subcommands ---------------------------------------------------


def test_init_creates_a_spec_and_refuses_to_clobber(tmp_path, monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "cluster", "init", "--name", "demo", cwd=tmp_path)
    assert code == 0
    assert "Created cluster 'demo'" in out
    assert load_spec(tmp_path).name == "demo"

    code, _, err = run(monkeypatch, capsys, "cluster", "init", "--name", "demo", cwd=tmp_path)
    assert code == 1
    assert "already contains a cluster spec" in err


def test_init_defaults_the_name_to_the_directory(tmp_path, monkeypatch, capsys):
    target = tmp_path / "platform"
    target.mkdir()
    run(monkeypatch, capsys, "cluster", "init", str(target), cwd=tmp_path)

    assert load_spec(target).name == "platform"


def test_add_records_the_tag_url_and_local_path(tmp_path, monkeypatch, capsys):
    write_member(tmp_path, "alpha", origin="git@github.com:org/alpha.git")
    cluster_dir = tmp_path / "cluster"
    cluster_dir.mkdir()
    run(monkeypatch, capsys, "cluster", "init", "--name", "demo", cwd=cluster_dir)

    code, out, _ = run(monkeypatch, capsys, "cluster", "add", "../alpha", cwd=cluster_dir)
    assert code == 0
    assert "Added member 'alpha'" in out

    spec = load_spec(cluster_dir)
    assert spec.tags == ["alpha"]
    assert spec.members[0].url == "git@github.com:org/alpha.git"
    # The absolute checkout path is machine-local, so it stays out of the
    # committed spec and lands in cluster.local.json instead.
    assert load_local_config(cluster_dir)["paths"]["alpha"] == "../alpha"
    assert not spec.members[0].path


def test_add_accepts_a_url_and_an_explicit_tag(tmp_path, monkeypatch, capsys):
    cluster_dir = tmp_path / "cluster"
    cluster_dir.mkdir()
    run(monkeypatch, capsys, "cluster", "init", "--name", "demo", cwd=cluster_dir)
    run(monkeypatch, capsys, "cluster", "add",
        "https://github.com/org/service.git", "--as", "svc", cwd=cluster_dir)

    spec = load_spec(cluster_dir)
    assert spec.tags == ["svc"]
    assert spec.members[0].url == "https://github.com/org/service.git"
    assert load_local_config(cluster_dir)["paths"] == {}


def test_add_refuses_a_duplicate_tag(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, _, err = run(monkeypatch, capsys, "cluster", "add", "../alpha", cwd=cluster_dir)

    assert code == 1
    assert "already has a member tagged 'alpha'" in err


def test_add_rejects_a_reserved_tag(tmp_path, monkeypatch, capsys):
    cluster_dir = tmp_path / "cluster"
    cluster_dir.mkdir()
    run(monkeypatch, capsys, "cluster", "init", "--name", "demo", cwd=cluster_dir)
    code, _, err = run(monkeypatch, capsys, "cluster", "add",
                       "https://github.com/o/r.git", "--as", "cluster", cwd=cluster_dir)

    assert code == 1
    assert "reserved" in err


def test_remove_drops_the_member_and_its_local_path(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    from kb_core.cluster_graph import save_local_config
    save_local_config(cluster_dir, {"paths": {"alpha": "../alpha"}})

    code, out, _ = run(monkeypatch, capsys, "cluster", "remove", "alpha", cwd=cluster_dir)
    assert code == 0
    assert "Removed member 'alpha'" in out
    assert load_spec(cluster_dir).tags == ["beta"]
    assert load_local_config(cluster_dir)["paths"] == {}


def test_remove_refuses_while_a_link_still_names_the_member(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    code, _, err = run(monkeypatch, capsys, "cluster", "remove", "alpha", cwd=cluster_dir)

    assert code == 1
    assert "still named by links" in err
    assert load_spec(cluster_dir).tags == ["alpha", "beta"]


def test_remove_reports_an_unknown_tag(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, _, err = run(monkeypatch, capsys, "cluster", "remove", "ghost", cwd=cluster_dir)

    assert code == 1
    assert "no member tagged 'ghost'" in err


def test_locate_writes_a_relative_local_path(tmp_path, monkeypatch, capsys):
    write_member(tmp_path / "elsewhere", "alpha")
    cluster_dir = two_member_cluster(tmp_path)
    code, out, _ = run(monkeypatch, capsys, "cluster", "locate", "alpha",
                       str(tmp_path / "elsewhere" / "alpha"), cwd=cluster_dir)

    assert code == 0
    assert "located at" in out
    assert load_local_config(cluster_dir)["paths"]["alpha"] == "../elsewhere/alpha"


def test_locate_rejects_a_path_that_is_not_a_directory(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, _, err = run(monkeypatch, capsys, "cluster", "locate", "alpha",
                       str(tmp_path / "nope"), cwd=cluster_dir)

    assert code == 1
    assert "is not a directory" in err


def test_check_passes_on_a_healthy_cluster(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, out, _ = run(monkeypatch, capsys, "cluster", "check", cwd=cluster_dir)

    assert code == 0
    assert "2 member(s)" in out and "OK" in out


def test_check_exits_nonzero_so_ci_can_gate_on_it(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    (tmp_path / "alpha" / "kb-core-out" / "graph.json").unlink()
    code, _, err = run(monkeypatch, capsys, "cluster", "check", cwd=cluster_dir)

    assert code == 1
    assert "kb-core extract" in err


def test_status_reports_resolution_per_member(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    (tmp_path / "alpha" / "kb-core-out" / "graph.json").unlink()
    code, out, _ = run(monkeypatch, capsys, "cluster", "status", cwd=cluster_dir)

    assert code == 0
    assert "alpha" in out and "no graph" in out
    assert "beta" in out and "ok" in out


def test_status_on_an_empty_cluster_suggests_add(tmp_path, monkeypatch, capsys):
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {"schema_version": 1, "name": "demo", "members": []})
    code, out, _ = run(monkeypatch, capsys, "cluster", "status", cwd=cluster_dir)

    assert code == 0
    assert "cluster add" in out


def test_build_writes_the_composed_graph(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    code, out, _ = run(monkeypatch, capsys, "cluster", "build", cwd=cluster_dir)

    assert code == 0
    assert "Built cluster 'demo'" in out
    assert "api_call: linked" in out
    assert (cluster_dir / "kb-core-out" / "graph.json").is_file()


def test_build_dir_flag_targets_another_cluster(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, _, _ = run(monkeypatch, capsys, "cluster", "build",
                     f"--dir={cluster_dir}", cwd=tmp_path)

    assert code == 0
    assert (cluster_dir / "kb-core-out" / "graph.json").is_file()


def test_build_no_refs_leaves_members_unmarked(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    run(monkeypatch, capsys, "cluster", "build", "--no-refs", cwd=cluster_dir)

    assert not (tmp_path / "alpha" / "kb-core-out" / "cluster-ref.json").exists()


def test_unknown_subcommand_prints_usage(tmp_path, monkeypatch, capsys):
    code, _, err = run(monkeypatch, capsys, "cluster", "bogus", cwd=tmp_path)

    assert code == 1
    assert "unknown cluster command" in err
    assert "Usage: kb-core cluster" in err


def test_bare_cluster_prints_usage(tmp_path, monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "cluster", cwd=tmp_path)

    assert code == 1
    assert "Usage: kb-core cluster" in out


def test_unknown_option_is_refused(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path)
    code, _, err = run(monkeypatch, capsys, "cluster", "status", "--nope", cwd=cluster_dir)

    assert code == 1
    assert "unknown option --nope" in err


# --- --cluster on the read-only commands -----------------------------------


@pytest.fixture
def built_cluster(tmp_path, monkeypatch, capsys):
    cluster_dir = two_member_cluster(tmp_path, links=[
        {"type": "api_call", "from": "beta:id:src_lib", "to": "alpha:id:src_lib"},
    ])
    build_cluster(cluster_dir)
    return cluster_dir


@pytest.mark.parametrize("cmd", ["query", "explain"])
def test_cluster_flag_reads_the_composed_graph(built_cluster, tmp_path, monkeypatch,
                                               capsys, cmd):
    code, out, _ = run(monkeypatch, capsys, cmd, "lib.py", "--cluster",
                       cwd=tmp_path / "beta")

    assert code == 0
    assert "alpha::src_lib" in out or "cluster" in out.lower()


def test_affected_crosses_the_repo_boundary(built_cluster, tmp_path, monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "affected", "alpha::src_lib", "--cluster",
                       cwd=tmp_path / "beta")

    assert code == 0
    assert "calls_api" in out


def test_path_traverses_a_declared_link(tmp_path, monkeypatch, capsys):
    # Distinct labels per member: the default fixture gives both repos the same
    # ones, and the endpoint resolver then picks a same-repo pair for which the
    # shortest path never needs the declared link.
    write_member(tmp_path, "alpha")
    write_member(tmp_path, "beta", nodes=[
        {"id": "src_caller", "label": "caller.py", "file_type": "code",
         "source_file": "src/caller.py", "source_location": "L1", "community": 0},
    ], links=[])
    cluster_dir = tmp_path / "cluster"
    write_spec(cluster_dir, {
        "schema_version": 1, "name": "demo",
        "members": [{"tag": "alpha"}, {"tag": "beta"}],
        "links": [{"type": "api_call", "from": "beta:id:src_caller",
                   "to": "alpha:id:src_lib_start"}],
    })
    build_cluster(cluster_dir)

    code, out, _ = run(monkeypatch, capsys, "path", "caller.py", "parse()",
                       "--cluster", cwd=tmp_path / "beta")

    assert code == 0
    assert "calls_api" in out


def test_named_cluster_selects_among_several(tmp_path, monkeypatch, capsys):
    write_member(tmp_path, "alpha")
    write_member(tmp_path, "beta")
    from kb_core.cluster_graph import save_local_config
    for holder, name in (("one", "left"), ("two", "right")):
        write_spec(tmp_path / holder, {
            "schema_version": 1, "name": name,
            "members": [{"tag": "alpha"}, {"tag": "beta"}],
        })
        save_local_config(tmp_path / holder,
                          {"paths": {"alpha": "../alpha", "beta": "../beta"}})
        build_cluster(tmp_path / holder)

    code, _, err = run(monkeypatch, capsys, "query", "lib", "--cluster", cwd=tmp_path / "beta")
    assert code == 1
    assert "member of 2 clusters" in err

    code, out, _ = run(monkeypatch, capsys, "query", "lib", "--cluster", "right",
                       cwd=tmp_path / "beta")
    assert code == 0
    assert str(tmp_path / "two").replace("\\", "/") in out.replace("\\", "/")


def test_cluster_and_graph_are_mutually_exclusive(built_cluster, tmp_path, monkeypatch, capsys):
    code, _, err = run(monkeypatch, capsys, "query", "lib", "--cluster",
                       "--graph", "x.json", cwd=tmp_path / "beta")

    assert code == 1
    assert "mutually exclusive" in err


def test_cluster_flag_outside_any_cluster_names_the_fix(tmp_path, monkeypatch, capsys):
    write_member(tmp_path, "alpha")
    code, _, err = run(monkeypatch, capsys, "query", "lib", "--cluster",
                       cwd=tmp_path / "alpha")

    assert code == 1
    assert "not a member of any cluster" in err


def test_unresolvable_cluster_directory_is_reported(built_cluster, tmp_path,
                                                    monkeypatch, capsys):
    # Break the hint and remove the spec so sibling discovery finds nothing.
    (built_cluster / "cluster.json").unlink()
    code, _, err = run(monkeypatch, capsys, "query", "lib", "--cluster",
                       cwd=tmp_path / "beta")

    assert code == 1
    assert "Cannot locate the directory for cluster 'demo'" in err


def test_a_miss_on_the_local_graph_suggests_the_cluster(built_cluster, tmp_path,
                                                        monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "query", "zzz-no-such-node",
                       cwd=tmp_path / "beta")

    assert code == 0
    assert "member of cluster 'demo'" in out
    assert "--cluster" in out


def test_no_hint_when_the_query_hit(built_cluster, tmp_path, monkeypatch, capsys):
    code, out, _ = run(monkeypatch, capsys, "query", "lib.py", cwd=tmp_path / "beta")

    assert code == 0
    assert "member of cluster" not in out


def test_no_hint_when_the_caller_named_a_graph(built_cluster, tmp_path, monkeypatch, capsys):
    graph = tmp_path / "beta" / "kb-core-out" / "graph.json"
    code, out, _ = run(monkeypatch, capsys, "query", "zzz-no-such-node",
                       "--graph", str(graph), cwd=tmp_path / "beta")

    assert code == 0
    assert "member of cluster" not in out


def test_cluster_ref_marker_names_every_member(built_cluster, tmp_path):
    payload = json.loads(
        (tmp_path / "beta" / "kb-core-out" / "cluster-ref.json").read_text(encoding="utf-8")
    )
    entry = payload["clusters"][0]

    assert entry["self_tag"] == "beta"
    assert [m["tag"] for m in entry["members"]] == ["alpha", "beta"]
