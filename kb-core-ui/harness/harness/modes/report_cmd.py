from __future__ import annotations

import argparse
from pathlib import Path

from harness.report import read_report, render_json, render_text


def run_report(args: argparse.Namespace) -> int:
    report = read_report(Path(args.in_path))
    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 0 if report.failed == 0 and report.errored == 0 else 1
