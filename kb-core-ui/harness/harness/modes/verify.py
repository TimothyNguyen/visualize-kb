from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from harness.baseline import baseline_path, read_baseline
from harness.canonical import NormalizeContext, canonicalize, to_comparable
from harness.diff import diff_case
from harness.engines import ResolvedEngine, bin_override_for, get_engine
from harness.errors import HarnessError
from harness.manifest import discover_fixtures
from harness.operations import SessionPool, execute_operation
from harness.report import ParityResult, RunReport, render_text, write_report
from harness.runner import ProcessRunner


def run_verify(args: argparse.Namespace) -> int:
    fixtures_dir = Path(args.fixtures_dir)
    try:
        fixtures = discover_fixtures(fixtures_dir)
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1

    fixtures_by_name = {f.name: f for f in fixtures}
    ops_by_fixture_op = {
        (f.name, op.id): op for f in fixtures for op in f.operations
    }

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
            path = baseline_path(fixtures_dir, fixture.name, op.id)
            if not path.exists():
                report.results.append(
                    ParityResult(
                        fixture=fixture.name,
                        operation_id=op.id,
                        oracle_engine="baseline",
                        candidate_engine="fresh",
                        error=f"no baseline found at {path}",
                    )
                )
                report.errored += 1
                continue

            case = read_baseline(path)
            try:
                engine = _resolve_engine(case.engine)
            except HarnessError as exc:
                report.results.append(
                    ParityResult(
                        fixture=fixture.name,
                        operation_id=op.id,
                        oracle_engine=case.engine,
                        candidate_engine="fresh",
                        error=str(exc),
                    )
                )
                report.errored += 1
                continue

            runner = ProcessRunner(engine, Path(args.work_dir))
            ctx = runner.prepare_run(fixture, f"verify-{fixture.name}")
            try:
                with SessionPool(runner, ctx) as sessions:
                    raw = execute_operation(runner, ctx, op, engine, sessions)
                    comparable_raw = to_comparable(op.capture, raw)
                    norm_ctx = NormalizeContext(fixture_root=str(ctx.fixture_root), engine=engine.config.name)
                    fresh = canonicalize(comparable_raw, case.normalizers, norm_ctx)
            except HarnessError as exc:
                report.results.append(
                    ParityResult(
                        fixture=fixture.name,
                        operation_id=op.id,
                        oracle_engine=case.engine,
                        candidate_engine="fresh",
                        error=str(exc),
                    )
                )
                report.errored += 1
                continue
            finally:
                if not args.keep_work_dir:
                    runner.cleanup(ctx)

            diff = diff_case(f"{fixture.name}/{op.id}", case.comparable, fresh, case.ignore_fields)
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

    for path in sorted(fixtures_dir.glob("*/baseline/*.json")):
        fixture_name = path.parent.parent.name
        op_id = path.stem
        if (fixture_name, op_id) in checked:
            continue
        fixture = fixtures_by_name.get(fixture_name)
        if fixture is None or (fixture_name, op_id) not in ops_by_fixture_op:
            report.results.append(
                ParityResult(
                    fixture=fixture_name,
                    operation_id=op_id,
                    oracle_engine="baseline",
                    candidate_engine="fresh",
                    error=f"orphaned baseline {path}: no matching fixture/operation in current manifest",
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
