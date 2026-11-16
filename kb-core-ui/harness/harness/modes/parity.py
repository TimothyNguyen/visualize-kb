from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any

from harness.canonical import NormalizeContext, canonicalize, to_comparable
from harness.diff import diff_case
from harness.engines import ResolvedEngine, bin_override_for, get_engine
from harness.errors import HarnessError
from harness.manifest import Fixture
from harness.operations import SessionPool, execute_operation
from harness.report import ParityResult, RunReport, render_text, write_report
from harness.runner import ProcessRunner


def _run_engine_ops(
    runner: ProcessRunner,
    fixture: Fixture,
    engine: ResolvedEngine,
    label: str,
    keep_work_dir: bool,
) -> dict[str, Any]:
    ctx = runner.prepare_run(fixture, f"{label}-{fixture.name}")
    results: dict[str, Any] = {}
    try:
        with SessionPool(runner, ctx) as sessions:
            for op in fixture.operations:
                raw = execute_operation(runner, ctx, op, engine, sessions)
                comparable_raw = to_comparable(op.capture, raw)
                norm_ctx = NormalizeContext(fixture_root=str(ctx.fixture_root), engine=engine.config.name)
                results[op.id] = canonicalize(comparable_raw, op.normalizers, norm_ctx)
    finally:
        if not keep_work_dir:
            runner.cleanup(ctx)
    return results


def run_parity(args: argparse.Namespace) -> int:
    fixtures_dir = Path(args.fixtures_dir)
    try:
        from harness.manifest import discover_fixtures

        fixtures = discover_fixtures(fixtures_dir)
        oracle_engine = get_engine(args.oracle, bin_override=bin_override_for(args, args.oracle))
        candidate_engine = get_engine(args.candidate, bin_override=bin_override_for(args, args.candidate))
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1

    oracle_runner = ProcessRunner(oracle_engine, Path(args.work_dir))
    candidate_runner = ProcessRunner(candidate_engine, Path(args.work_dir))

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    report = RunReport(
        mode="parity",
        started_at=started_at,
        finished_at=started_at,
        engine_pair=(oracle_engine.config.name, candidate_engine.config.name),
    )

    for fixture in fixtures:
        oracle_by_op: dict[str, Any] | None = None
        candidate_by_op: dict[str, Any] | None = None
        oracle_error: str | None = None
        candidate_error: str | None = None

        try:
            oracle_by_op = _run_engine_ops(oracle_runner, fixture, oracle_engine, "oracle", args.keep_work_dir)
        except HarnessError as exc:
            oracle_error = str(exc)

        try:
            candidate_by_op = _run_engine_ops(
                candidate_runner, fixture, candidate_engine, "candidate", args.keep_work_dir
            )
        except HarnessError as exc:
            candidate_error = str(exc)

        for op in fixture.operations:
            case_id = f"{fixture.name}/{op.id}"
            if oracle_error is not None or candidate_error is not None:
                err = oracle_error or candidate_error
                report.results.append(
                    ParityResult(
                        fixture=fixture.name,
                        operation_id=op.id,
                        oracle_engine=oracle_engine.config.name,
                        candidate_engine=candidate_engine.config.name,
                        error=err,
                    )
                )
                report.errored += 1
                continue

            diff = diff_case(case_id, oracle_by_op[op.id], candidate_by_op[op.id], op.ignore_fields)
            report.results.append(
                ParityResult(
                    fixture=fixture.name,
                    operation_id=op.id,
                    oracle_engine=oracle_engine.config.name,
                    candidate_engine=candidate_engine.config.name,
                    diff=diff,
                )
            )
            if diff.equal:
                report.passed += 1
            else:
                report.failed += 1

    report.finished_at = dt.datetime.now(dt.timezone.utc).isoformat()

    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        stamp = report.finished_at.replace(":", "").replace("-", "").replace(".", "")
        out_dir = Path(args.work_dir) / "runs" / f"{stamp}-parity"
    out_path = out_dir / "report.json"
    write_report(out_path, report)

    print(render_text(report))
    print(f"report written to {out_path}")

    return 0 if report.failed == 0 and report.errored == 0 else 1
