from __future__ import annotations

import argparse


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--fixtures-dir", default="tests/fixtures")
    sp.add_argument("--work-dir", default=".harness-work")
    sp.add_argument("--go-bin", default=None)
    sp.add_argument("--python-bin", default=None)
    sp.add_argument("--keep-work-dir", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_record = sub.add_parser("record", help="run an engine and write baselines")
    _add_common_flags(p_record)
    p_record.add_argument("--engine", default="go")

    p_parity = sub.add_parser("parity", help="run two engines and diff their outputs")
    _add_common_flags(p_parity)
    p_parity.add_argument("--oracle", default="go")
    p_parity.add_argument("--candidate", default="go")
    p_parity.add_argument("--out-dir", default=None)

    p_verify = sub.add_parser("verify", help="re-run baselines against their recorded engine")
    _add_common_flags(p_verify)

    p_report = sub.add_parser("report", help="render a prior report.json")
    p_report.add_argument("--in", dest="in_path", required=True)
    p_report.add_argument("--format", choices=["text", "json"], default="text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "record":
        from harness.modes.record import run_record

        return run_record(args)
    if args.mode == "parity":
        from harness.modes.parity import run_parity

        return run_parity(args)
    if args.mode == "verify":
        from harness.modes.verify import run_verify

        return run_verify(args)
    if args.mode == "report":
        from harness.modes.report_cmd import run_report

        return run_report(args)

    parser.error(f"unknown mode {args.mode}")
    return 2
