from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from harness import __version__
from harness.baseline import RecordedCase, baseline_path, write_baseline
from harness.canonical import NormalizeContext, canonicalize, to_comparable
from harness.engines import bin_override_for, get_engine
from harness.errors import HarnessError
from harness.manifest import discover_fixtures
from harness.operations import SessionPool, execute_operation
from harness.runner import ProcessRunner


def run_record(args: argparse.Namespace) -> int:
    fixtures_dir = Path(args.fixtures_dir)
    try:
        fixtures = discover_fixtures(fixtures_dir)
        engine = get_engine(args.engine, bin_override=bin_override_for(args, args.engine))
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1

    runner = ProcessRunner(engine, Path(args.work_dir))
    had_error = False

    for fixture in fixtures:
        ctx = runner.prepare_run(fixture, f"record-{fixture.name}")
        try:
            with SessionPool(runner, ctx) as sessions:
                for op in fixture.operations:
                    try:
                        raw = execute_operation(runner, ctx, op, engine, sessions)
                        comparable_raw = to_comparable(op.capture, raw)
                        norm_ctx = NormalizeContext(
                            fixture_root=str(ctx.fixture_root), engine=engine.config.name
                        )
                        comparable = canonicalize(comparable_raw, op.normalizers, norm_ctx)
                    except HarnessError as exc:
                        print(f"error: {fixture.name}/{op.id}: {exc}")
                        had_error = True
                        continue

                    case = RecordedCase(
                        fixture=fixture.name,
                        operation_id=op.id,
                        engine=engine.config.name,
                        captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                        harness_version=__version__,
                        normalizers=op.normalizers,
                        ignore_fields=op.ignore_fields,
                        comparable=comparable,
                    )
                    path = baseline_path(fixtures_dir, fixture.name, op.id)
                    write_baseline(path, case)
                    print(f"recorded {fixture.name}/{op.id} -> {path}")
        finally:
            if not args.keep_work_dir:
                runner.cleanup(ctx)

    return 1 if had_error else 0
