from __future__ import annotations

from pathlib import Path

from conftest import make_args
from harness.engines import get_engine
from harness.manifest import discover_fixtures
from harness.modes.parity import _run_engine_ops, run_parity
from harness.report import read_report
from harness.runner import ProcessRunner


def _run_fixture(fixtures_dir: Path, go_bin: str, tmp_path: Path, fixture_name: str) -> dict:
    engine = get_engine("go", bin_override=go_bin)
    fixture = next(f for f in discover_fixtures(fixtures_dir) if f.name == fixture_name)
    runner = ProcessRunner(engine, tmp_path / "work")
    return _run_engine_ops(runner, fixture, engine, "matrix-test", keep_work_dir=False)


def test_full_matrix_go_vs_go_zero_diff(go_bin, fixtures_dir: Path, tmp_path: Path):
    args = make_args(
        "parity",
        fixtures_dir=str(fixtures_dir),
        work_dir=str(tmp_path / "work"),
        go_bin=go_bin,
        out_dir=str(tmp_path / "out"),
    )
    rc = run_parity(args)
    report = read_report(tmp_path / "out" / "report.json")
    assert rc == 0, [r.error or r.diff for r in report.results if r.error or (r.diff and not r.diff.equal)]
    assert report.failed == 0
    assert report.errored == 0


def test_go_basics_symbols_have_expected_shape(go_bin, fixtures_dir: Path, tmp_path: Path):
    results = _run_fixture(fixtures_dir, go_bin, tmp_path, "go-basics")

    symbols = results["file-symbols"]["body"]
    by_name = {s["name"]: s for s in symbols}
    assert by_name["Add"]["kind"] == "function"
    assert by_name["Calculator"]["kind"] == "class"
    assert by_name["Adder"]["kind"] == "interface"
    assert by_name["DefaultStart"]["kind"] == "const"
    # file-symbols is top-level-only (parent_id filter) — methods excluded.
    assert "AddTo" not in by_name

    graph = results["graph"]["body"]
    nodes_by_name = {n["name"]: n for n in graph["nodes"]}
    assert nodes_by_name["AddTo"]["kind"] == "method"
    add_to_id = nodes_by_name["AddTo"]["id"]
    add_id = nodes_by_name["Add"]["id"]
    assert any(
        e["kind"] == "calls" and e["source"] == add_to_id and e["target"] == add_id
        for e in graph["edges"]
    )


def test_malformed_repo_parses_without_crashing(go_bin, fixtures_dir: Path, tmp_path: Path):
    results = _run_fixture(fixtures_dir, go_bin, tmp_path, "malformed")

    assert results["parse-exit"]["exit_code"] == 0

    names = {n["name"] for n in results["graph"]["body"]["nodes"]}
    assert "Ok" in names


def test_changed_file_reflects_renamed_symbol(go_bin, fixtures_dir: Path, tmp_path: Path):
    results = _run_fixture(fixtures_dir, go_bin, tmp_path, "changed-file")

    names = {n["name"] for n in results["graph-after-change"]["body"]["nodes"]}
    assert "AddTwo" in names
    assert "Add" not in names


def test_deleted_file_prunes_symbols_and_edges(go_bin, fixtures_dir: Path, tmp_path: Path):
    results = _run_fixture(fixtures_dir, go_bin, tmp_path, "deleted-file")

    body = results["graph-after-delete"]["body"]
    names = {n["name"] for n in body["nodes"]}
    assert "A" in names
    assert "B" not in names
    assert all("B" not in (e["source"] + e["target"]) for e in body["edges"])
