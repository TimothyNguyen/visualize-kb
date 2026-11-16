"""Port of internal/bots/runner_test.go."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

from kb_core_ui.bots import (
    MissingArgError,
    Runner,
    UnknownBotError,
    build_args,
    lookup,
)


@pytest.fixture
def fake_bin(tmp_path):
    """Stands in for the real kb-core-ui binary so the runner is tested
    hermetically. Go's version is a shell script; a Python one runs on Windows
    too, which is where this port is developed."""

    def make(exit_code: int) -> list[str]:
        script = tmp_path / f"fake-kb-core-ui-{exit_code}.py"
        script.write_text(
            textwrap.dedent(
                f"""
                import sys
                print("args: " + " ".join(sys.argv[1:]))
                sys.exit({exit_code})
                """
            ),
            encoding="utf-8",
        )
        return [sys.executable, str(script)]

    return make


def wait_done(runner: Runner, run_id: str):
    deadline = time.time() + 5
    while time.time() < deadline:
        run = runner.get(run_id)
        assert run is not None, f"run {run_id} vanished"
        if run.status != "running":
            return run
        time.sleep(0.02)
    pytest.fail(f"run {run_id} did not finish in time")


def test_runner_succeeds(fake_bin, tmp_path):
    r = Runner(fake_bin(0), str(tmp_path))
    run = r.start("graph-sync", None)
    assert run.status == "running"

    done = wait_done(r, run.id)
    assert done.status == "succeeded"
    assert done.exit_code == 0
    assert "bot graph-sync" in done.output
    assert "--repo" in done.output


def test_runner_fail_propagates_exit_code(fake_bin, tmp_path):
    r = Runner(fake_bin(2), str(tmp_path))
    done = wait_done(r, r.start("graph-sync", None).id)
    assert (done.status, done.exit_code) == ("failed", 2)


def test_runner_rejects_unknown_bot(fake_bin, tmp_path):
    r = Runner(fake_bin(0), str(tmp_path))
    with pytest.raises(UnknownBotError):
        r.start("does-not-exist", None)


def test_runner_requires_required_arg(fake_bin, tmp_path):
    r = Runner(fake_bin(0), str(tmp_path))
    with pytest.raises(MissingArgError):
        r.start("pr-review", None)


def test_build_args_positional_and_flags():
    args = build_args(lookup("pr-review"), {"pr_number": "12", "dry_run": "true"}, "/repo")
    assert args == ["bot", "pr-review", "12", "--dry-run", "--repo", "/repo"]


def test_build_args_dry_run_false_omits_flag():
    args = build_args(lookup("pr-review"), {"pr_number": "5", "dry_run": "false"}, "/repo")
    assert "--dry-run" not in args


def test_list_newest_first(fake_bin, tmp_path):
    r = Runner(fake_bin(0), str(tmp_path))
    first = r.start("graph-sync", None)
    wait_done(r, first.id)
    second = r.start("doctor", None)
    wait_done(r, second.id)

    runs = r.list()
    assert [run.id for run in runs] == [second.id, first.id]


@pytest.mark.parametrize(
    "bot,args,want",
    [
        ("commit-check", {"ref": "HEAD~1"}, ["bot", "commit-check", "HEAD~1", "--repo", "/r"]),
        ("commit-check", {}, ["bot", "commit-check", "", "--repo", "/r"]),
        ("test-writer", {"target": "BuildFlat", "write": "true"},
         ["bot", "test-writer", "BuildFlat", "--write", "--repo", "/r"]),
        ("test-writer", {"target": "BuildFlat", "write": "false"},
         ["bot", "test-writer", "BuildFlat", "--repo", "/r"]),
        ("anomaly-scan", {"focus": "server"},
         ["bot", "anomaly-scan", "--focus", "server", "--repo", "/r"]),
        ("anomaly-scan", {}, ["bot", "anomaly-scan", "--repo", "/r"]),
        ("feature-verdict", {"feature": "add delete endpoint"},
         ["bot", "feature-verdict", "add delete endpoint", "--repo", "/r"]),
        ("triage", {"issue": "7", "comment": "true"},
         ["bot", "triage", "7", "--comment", "--repo", "/r"]),
    ],
)
def test_build_args_new_bots(bot, args, want):
    assert build_args(lookup(bot), args, "/r") == want


@pytest.fixture
def bot_scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "bots"))
    import common
    import preflight
    import pr_review

    return common, preflight, pr_review


def test_bot_runtime_defaults_to_current_python_entry_point(bot_scripts, monkeypatch, tmp_path):
    common, preflight, pr_review = bot_scripts
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    binary = scripts / ("kb-core-ui.exe" if os.name == "nt" else "kb-core-ui")
    binary.touch(mode=0o755)
    monkeypatch.setattr("sysconfig.get_path", lambda name: str(scripts))
    monkeypatch.setattr("shutil.which", lambda name: "/stale/go/kb-core-ui")
    monkeypatch.setenv("KB_CORE_UI_BIN", "/oracle/go/kb-core-ui")
    for module in bot_scripts:
        assert module.find_kb_core_ui_bin(None) == str(binary)
        assert module.find_kb_core_ui_bin("/explicit/go") == "/explicit/go"

    config = common.build_mcp_config(str(binary), tmp_path, tmp_path)
    assert json.loads(config.read_text())["mcpServers"]["kb-core-ui"] == {
        "command": str(binary), "args": ["mcp", str(tmp_path)]
    }


def test_bot_runtime_missing_python_does_not_fall_back_to_go(bot_scripts, monkeypatch, tmp_path):
    common, preflight, pr_review = bot_scripts
    monkeypatch.setattr("sysconfig.get_path", lambda name: str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda name: "/stale/go/kb-core-ui")
    for module in (common, pr_review):
        with pytest.raises(RuntimeError, match="pip install"):
            module.find_kb_core_ui_bin(None)
    assert preflight.find_kb_core_ui_bin() is None


@pytest.mark.parametrize("exit_code", [0, 2])
def test_bot_script_keeps_current_interpreter(monkeypatch, tmp_path, exit_code):
    from kb_core_ui.cli.root import run_bot_script

    script = tmp_path / "bot.py"
    script.touch()
    calls = []

    def call(argv):
        calls.append(argv)
        return exit_code

    monkeypatch.setattr("kb_core_ui.cli.root.subprocess.call", call)
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            run_bot_script(script.name, str(tmp_path), ["--repo", "R"])
        assert exc.value.code == exit_code
    else:
        run_bot_script(script.name, str(tmp_path), ["--repo", "R"])
    assert calls == [[sys.executable, str(script), "--repo", "R"]]
