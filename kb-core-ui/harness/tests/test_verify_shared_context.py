"""verify must replay a fixture the way record recorded it.

`record` writes every baseline from one shared RunContext per fixture, so a
mutating operation earlier in the manifest is visible to a later one. If
`verify` gave each operation its own throwaway context, any stateful fixture
would fail against preconditions the recording never had (spec/SPEC.md B7).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import __version__
from harness.baseline import RecordedCase, baseline_path, write_baseline
from harness.modes.verify import run_verify

FIXTURE = {
    "name": "stateful",
    "repo": "repo",
    "operations": [
        {"id": "mutate", "kind": "cli", "command": "touch"},
        {"id": "observe", "kind": "cli", "command": "count"},
    ],
}


class _RecordingRunner:
    """Stands in for ProcessRunner: counts how many fixture copies get made
    and lets the two fake CLI commands share state through that copy."""

    prepared: list[Path] = []

    def __init__(self, engine, work_root, **kwargs):
        self.engine = engine
        self.work_root = Path(work_root)

    def prepare_run(self, fixture, run_label):
        from harness.runner import RunContext

        root = self.work_root / f"{run_label}-{len(_RecordingRunner.prepared)}"
        (root / "repo").mkdir(parents=True)
        _RecordingRunner.prepared.append(root)
        return RunContext(
            run_id=str(len(_RecordingRunner.prepared)),
            engine_name="fake",
            root=root,
            fixture_root=root / "repo",
            db_path=root / "graph.db",
            work_dir=root,
        )

    def run_cli(self, ctx, command, values):
        from harness.runner import CliResult

        marker = ctx.fixture_root / "marker"
        if command == "touch":
            marker.write_text("1", encoding="utf-8")
            stdout = "touched\n"
        else:
            stdout = f"count={1 if marker.exists() else 0}\n"
        return CliResult(argv=[command], exit_code=0, stdout=stdout, stderr="", duration_s=0.0)

    def cleanup(self, ctx):
        pass


def _write_fixture(fixtures_dir: Path) -> None:
    fixture_dir = fixtures_dir / "stateful"
    (fixture_dir / "repo").mkdir(parents=True)
    (fixture_dir / "manifest.json").write_text(json.dumps(FIXTURE), encoding="utf-8")

    for op_id, stdout in (("mutate", "touched\n"), ("observe", "count=1\n")):
        write_baseline(
            baseline_path(fixtures_dir, "stateful", op_id),
            RecordedCase(
                fixture="stateful",
                operation_id=op_id,
                engine="fake",
                captured_at="2026-08-28T00:00:00+00:00",
                harness_version=__version__,
                normalizers=[],
                ignore_fields=[],
                comparable={"exit_code": 0, "stdout": stdout},
            ),
        )


def test_verify_replays_a_fixture_in_one_context(tmp_path, monkeypatch, capsys):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    _write_fixture(fixtures_dir)

    _RecordingRunner.prepared = []
    monkeypatch.setattr("harness.modes.verify.ProcessRunner", _RecordingRunner)
    monkeypatch.setattr(
        "harness.modes.verify.get_engine",
        lambda name, bin_override=None: type(
            "E", (), {"config": type("C", (), {"name": name})()}
        )(),
    )

    args = argparse.Namespace(
        fixtures_dir=str(fixtures_dir),
        work_dir=str(tmp_path / "work"),
        keep_work_dir=True,
        verbose=False,
        go_bin=None,
        python_bin=None,
    )
    assert run_verify(args) == 0, capsys.readouterr().out

    # One context for the whole fixture: "observe" must see "mutate"'s effect.
    assert len(_RecordingRunner.prepared) == 1
