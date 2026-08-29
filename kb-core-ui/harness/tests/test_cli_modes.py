from __future__ import annotations

import pytest

from harness.cli import build_parser, main


def test_build_parser_record_defaults():
    args = build_parser().parse_args(["record"])
    assert args.mode == "record"
    assert args.engine == "go"
    assert args.fixtures_dir == "tests/fixtures"
    assert args.work_dir == ".harness-work"
    assert args.keep_work_dir is False


def test_build_parser_parity_defaults():
    args = build_parser().parse_args(["parity"])
    assert args.mode == "parity"
    assert args.oracle == "go"
    assert args.candidate == "go"
    assert args.out_dir is None


def test_build_parser_parity_overrides():
    args = build_parser().parse_args(
        ["parity", "--oracle", "go", "--candidate", "python", "--out-dir", "out"]
    )
    assert args.candidate == "python"
    assert args.out_dir == "out"


def test_build_parser_verify_defaults():
    args = build_parser().parse_args(["verify"])
    assert args.mode == "verify"
    assert args.fixtures_dir == "tests/fixtures"


def test_build_parser_report_requires_in():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["report"])
    args = build_parser().parse_args(["report", "--in", "report.json"])
    assert args.in_path == "report.json"
    assert args.format == "text"


def test_build_parser_requires_a_mode():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_main_dispatches_to_record(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr("harness.modes.record.run_record", lambda args: calls.append(("record", args)) or 0)
    assert main(["record"]) == 0
    assert calls[0][0] == "record"


def test_main_dispatches_to_parity(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr("harness.modes.parity.run_parity", lambda args: calls.append(("parity", args)) or 0)
    assert main(["parity"]) == 0
    assert calls[0][0] == "parity"


def test_main_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr("harness.modes.verify.run_verify", lambda args: calls.append(("verify", args)) or 0)
    assert main(["verify"]) == 0
    assert calls[0][0] == "verify"


def test_main_dispatches_to_report(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(
        "harness.modes.report_cmd.run_report", lambda args: calls.append(("report", args)) or 0
    )
    assert main(["report", "--in", "x.json"]) == 0
    assert calls[0][0] == "report"
