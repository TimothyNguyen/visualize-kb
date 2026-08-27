from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import make_args
from harness.baseline import baseline_path, read_baseline, write_baseline
from harness.engines import ENGINES, EngineConfig, get_engine
from harness.manifest import discover_fixtures
from harness.modes.parity import run_parity
from harness.modes.record import run_record
from harness.modes.verify import run_verify
from harness.report import read_report
from harness.runner import ProcessRunner


def test_go_vs_go_identical_zero_diff(go_bin, tmp_fixtures_dir: Path, tmp_path: Path):
    args = make_args(
        "parity",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "work"),
        go_bin=go_bin,
        out_dir=str(tmp_path / "out"),
    )
    rc = run_parity(args)
    report = read_report(tmp_path / "out" / "report.json")
    assert rc == 0, [r.error or r.diff for r in report.results if r.error or (r.diff and not r.diff.equal)]
    assert report.failed == 0
    assert report.errored == 0


def test_mutated_fixture_detected_via_verify(go_bin, tmp_fixtures_dir: Path, tmp_path: Path):
    record_args = make_args(
        "record",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "record-work"),
        go_bin=go_bin,
    )
    assert run_record(record_args) == 0

    hello_go = tmp_fixtures_dir / "smoke" / "repo" / "hello.go"
    hello_go.write_text(hello_go.read_text(encoding="utf-8").replace("Add", "AddTwo"), encoding="utf-8")

    verify_args = make_args(
        "verify",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "verify-work"),
        go_bin=go_bin,
        out_dir=str(tmp_path / "verify-out"),
    )
    rc = run_verify(verify_args)
    assert rc == 1

    graph_result = next(r for r in _read_verify_report(tmp_path) if r.operation_id == "rest-graph")
    assert graph_result.diff is not None
    assert not graph_result.diff.equal
    assert any("AddTwo" in str(e.candidate) for e in graph_result.diff.entries)


def _read_verify_report(tmp_path: Path):
    runs_dir = tmp_path / "verify-work" / "runs"
    report_path = sorted(runs_dir.glob("*-verify/report.json"))[-1]
    return read_report(report_path).results


def test_verify_detects_corrupted_baseline(go_bin, tmp_fixtures_dir: Path, tmp_path: Path):
    record_args = make_args(
        "record",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "record-work"),
        go_bin=go_bin,
    )
    assert run_record(record_args) == 0

    path = baseline_path(tmp_fixtures_dir, "smoke", "parse-ok")
    case = read_baseline(path)
    corrupted = dict(case.comparable)
    corrupted["exit_code"] = corrupted["exit_code"] + 1
    write_baseline(path, type(case)(**{**case.__dict__, "comparable": corrupted}))

    verify_args = make_args(
        "verify",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "verify-work"),
        go_bin=go_bin,
    )
    rc = run_verify(verify_args)
    assert rc == 1

    result = next(r for r in _read_verify_report(tmp_path) if r.operation_id == "parse-ok")
    assert result.diff is not None
    assert any(e.path == "$.exit_code" for e in result.diff.entries)


def test_isolated_temp_roots_and_dbs(go_bin, tmp_fixtures_dir: Path, tmp_path: Path):
    engine = get_engine("go", bin_override=go_bin)
    fixture = discover_fixtures(tmp_fixtures_dir)[0]
    runner = ProcessRunner(engine, tmp_path / "work")

    ctx1 = runner.prepare_run(fixture, "iso1")
    ctx2 = runner.prepare_run(fixture, "iso2")
    assert ctx1.fixture_root != ctx2.fixture_root

    add_result = runner.run_cli(ctx1, "memory_add", {"kind": "rule", "title": "t", "text": "txt"})
    assert add_result.exit_code == 0, add_result.stderr
    assert (ctx1.fixture_root / ".kb-core-ui" / "memory.db").exists()
    assert not (ctx2.fixture_root / ".kb-core-ui").exists()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(runner.run_cli, ctx1, "parse", {}),
            pool.submit(runner.run_cli, ctx2, "parse", {}),
        ]
        results = [f.result() for f in futures]
    assert all(r.exit_code == 0 for r in results), [r.stderr for r in results]


def test_engine_is_pure_config_addition(tmp_path: Path):
    fixture_dir = tmp_path / "fixtures" / "echo"
    (fixture_dir / "repo").mkdir(parents=True)
    (fixture_dir / "repo" / "placeholder.txt").write_text("x", encoding="utf-8")
    (fixture_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "echo",
                "repo": "repo",
                "operations": [
                    {
                        "id": "echo-op",
                        "kind": "cli",
                        "command": "identity",
                        "capture": "stdout_exit",
                        "normalizers": ["line_endings"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    identity_template = [sys.executable, "-c", "print('hello-parity')"]
    original = dict(ENGINES)
    try:
        ENGINES["fake-a"] = EngineConfig(
            name="fake-a", resolve_bin=lambda explicit: explicit or sys.executable,
            cli_templates={"identity": identity_template},
        )
        ENGINES["fake-b"] = EngineConfig(
            name="fake-b", resolve_bin=lambda explicit: explicit or sys.executable,
            cli_templates={"identity": identity_template},
        )

        args = make_args(
            "parity",
            fixtures_dir=str(tmp_path / "fixtures"),
            work_dir=str(tmp_path / "work"),
            oracle="fake-a",
            candidate="fake-b",
            out_dir=str(tmp_path / "out"),
        )
        rc = run_parity(args)
        report = read_report(tmp_path / "out" / "report.json")
        assert rc == 0
        assert report.failed == 0
        assert report.errored == 0
    finally:
        ENGINES.clear()
        ENGINES.update(original)


def test_all_capture_kinds(go_bin, tmp_fixtures_dir: Path, tmp_path: Path):
    args = make_args(
        "parity",
        fixtures_dir=str(tmp_fixtures_dir),
        work_dir=str(tmp_path / "work"),
        go_bin=go_bin,
        out_dir=str(tmp_path / "out"),
    )
    rc = run_parity(args)
    assert rc == 0

    report = read_report(tmp_path / "out" / "report.json")
    by_op = {r.operation_id: r for r in report.results}

    assert by_op["parse-ok"].diff.equal  # stdout_exit
    assert by_op["rest-stats"].diff.equal  # json_body_status
    assert by_op["mcp-get-tree"].diff.equal  # json_result
