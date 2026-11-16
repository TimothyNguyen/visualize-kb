from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from harness.baseline import RecordedCase, baseline_path, read_baseline
from harness.canonical import NormalizeContext, canonicalize, to_comparable
from harness.diff import diff_case
from harness.engines import ResolvedEngine, bin_override_for, get_engine
from harness.errors import HarnessError
from harness.manifest import Fixture, discover_fixtures
from harness.operations import SessionPool, execute_operation
from harness.report import ParityResult, RunReport, render_text, write_report
from harness.runner import ProcessRunner


def _error_result(fixture: str, op_id: str, engine: str, message: str) -> ParityResult:
    return ParityResult(
        fixture=fixture,
        operation_id=op_id,
        oracle_engine=engine,
        candidate_engine="fresh",
        error=message,
    )


def run_verify(args: argparse.Namespace) -> int:
    fixtures_dir = Path(args.fixtures_dir)
    try:
        fixtures = discover_fixtures(fixtures_dir)
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1

    fixtures_by_name = {f.name: f for f in fixtures}
    ops_by_fixture_op = {(f.name, op.id): op for f in fixtures for op in f.operations}

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    report = RunReport(
        mode="verify",
        started_at=started_at,
        finished_at=started_at,
        engine_pair=("baseline", "fresh"),
    )

    engine_cache: dict[str, ResolvedEngine] = {}

    def _resolve_engine(name: str) -> ResolvedEngine:
        if name not in engine_cache:
            engine_cache[name] = get_engine(name, bin_override=bin_override_for(args, name))
        return engine_cache[name]

    checked: set[tuple[str, str]] = set()

    for fixture in fixtures:
        for op in fixture.operations:
            checked.add((fixture.name, op.id))
        _verify_fixture(fixture, fixtures_dir, args, report, _resolve_engine)

    for path in sorted(fixtures_dir.glob("*/baseline/*.json")):
        fixture_name = path.parent.parent.name
        op_id = path.stem
        if (fixture_name, op_id) in checked:
            continue
        fixture = fixtures_by_name.get(fixture_name)
        if fixture is None or (fixture_name, op_id) not in ops_by_fixture_op:
            report.results.append(
                _error_result(
                    fixture_name,
                    op_id,
                    "baseline",
                    f"orphaned baseline {path}: no matching fixture/operation in current manifest",
                )
            )
            report.errored += 1

    report.finished_at = dt.datetime.now(dt.timezone.utc).isoformat()

    out_dir = Path(args.work_dir) / "runs" / f"{report.finished_at.replace(':', '').replace('-', '').replace('.', '')}-verify"
    out_path = out_dir / "report.json"
    write_report(out_path, report)

    print(render_text(report))
    print(f"report written to {out_path}")

    return 0 if report.failed == 0 and report.errored == 0 else 1


def _verify_fixture(
    fixture: Fixture,
    fixtures_dir: Path,
    args: argparse.Namespace,
    report: RunReport,
    resolve_engine,
) -> None:
    """Replays a whole fixture per engine, in manifest order, inside a single
    RunContext.

    `record` writes its baselines from exactly one shared context per fixture,
    so operations there observe each other's side effects — a POST /api/memory
    earlier in the list is still visible to a later GET /api/memory. Verifying
    each operation in its own throwaway context would compare a recorded
    result against different preconditions, and any stateful fixture would
    fail for a reason that has nothing to do with drift.
    """
    cases: dict[str, RecordedCase] = {}
    for op in fixture.operations:
        path = baseline_path(fixtures_dir, fixture.name, op.id)
        if not path.exists():
            report.results.append(
                _error_result(fixture.name, op.id, "baseline", f"no baseline found at {path}")
            )
            report.errored += 1
            continue
        cases[op.id] = read_baseline(path)

    if not cases:
        return

    # Baselines name the engine that recorded them. Ops recorded by different
    # engines get one replay each, and every op still executes in every pass so
    # the shared state a later op depends on is always built the same way.
    engine_names: list[str] = []
    for op in fixture.operations:
        case = cases.get(op.id)
        if case is not None and case.engine not in engine_names:
            engine_names.append(case.engine)

    for engine_name in engine_names:
        try:
            engine = resolve_engine(engine_name)
        except HarnessError as exc:
            for op in fixture.operations:
                if cases.get(op.id) is not None and cases[op.id].engine == engine_name:
                    report.results.append(
                        _error_result(fixture.name, op.id, engine_name, str(exc))
                    )
                    report.errored += 1
            continue

        _replay(fixture, engine, engine_name, cases, args, report)


def _replay(
    fixture: Fixture,
    engine: ResolvedEngine,
    engine_name: str,
    cases: dict[str, RecordedCase],
    args: argparse.Namespace,
    report: RunReport,
) -> None:
    runner = ProcessRunner(engine, Path(args.work_dir))
    ctx = runner.prepare_run(fixture, f"verify-{fixture.name}")
    try:
        with SessionPool(runner, ctx) as sessions:
            for op in fixture.operations:
                case = cases.get(op.id)
                try:
                    raw = execute_operation(runner, ctx, op, engine, sessions)
                except HarnessError as exc:
                    # record reports the failure and moves on rather than
                    # abandoning the fixture, so verify does too: one flaky
                    # serve start must not turn every later operation into a
                    # cascade of errors that hides the real result.
                    if case is not None and case.engine == engine_name:
                        report.results.append(
                            _error_result(fixture.name, op.id, engine_name, str(exc))
                        )
                        report.errored += 1
                    continue
                if case is None or case.engine != engine_name:
                    continue
                comparable_raw = to_comparable(op.capture, raw)
                norm_ctx = NormalizeContext(
                    fixture_root=str(ctx.fixture_root), engine=engine.config.name
                )
                fresh = canonicalize(comparable_raw, case.normalizers, norm_ctx)
                diff = diff_case(
                    f"{fixture.name}/{op.id}", case.comparable, fresh, case.ignore_fields
                )
                report.results.append(
                    ParityResult(
                        fixture=fixture.name,
                        operation_id=op.id,
                        oracle_engine=case.engine,
                        candidate_engine="fresh",
                        diff=diff,
                    )
                )
                if diff.equal:
                    report.passed += 1
                else:
                    report.failed += 1
    finally:
        if not args.keep_work_dir:
            runner.cleanup(ctx)
