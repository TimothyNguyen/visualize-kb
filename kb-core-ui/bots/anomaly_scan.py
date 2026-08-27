#!/usr/bin/env python3
"""Anomaly Detector bot — scan the codebase for abnormalities and risks.

Unlike the per-diff review bots, this looks at the codebase as a whole via
the graph and flags likely problems: possible breakages, cross-boundary
contract mismatches (backend returns X, frontend expects Y), code that
duplicates existing code instead of reusing it, and anything that violates
the project's stored rules (memory). Prints a ranked report.

Usage:
    kb-core-ui bot anomaly-scan [--repo PATH] [--focus "area or subsystem"]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common

PROMPT = """\
You are auditing this codebase for anomalies and risks. You have kb-core-ui's
MCP tools: get_stats and get_tree for the shape of the repo; search_symbol
/ get_symbol / get_callers / get_callees / get_file_slice to investigate;
and memory_search to load the project's primary RULES and past LESSONS —
call memory_search early and check the code against those rules.

{focus}

Hunt specifically for:
- cross-boundary contract mismatches: a caller/consumer assuming a
  shape/type/behavior the producer doesn't actually provide (e.g. backend
  returns a field the frontend never reads, or vice-versa). Verify with the
  graph before flagging.
- possible breakages: functions/routes whose contract looks fragile or
  inconsistent with their callers.
- duplication: near-identical functions that should be one (search_symbol
  by likely names).
- rule violations: anything contradicting a rule/lesson from memory_search.

Investigate before asserting — don't guess. It's better to report 5
verified anomalies than 30 speculative ones.

Respond with ONLY a fenced ```json block: an array of
{{"severity": "high"|"medium"|"low", "category": <slug>,
  "location": "<file or symbol>", "summary": <one sentence>,
  "evidence": <what in the graph/memory shows this>,
  "suggested_fix": <one sentence>}}.
Empty array [] if the codebase looks clean.
"""

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
SEV_MARK = {"high": "[HIGH]", "medium": "[MED ]", "low": "[LOW ]"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--kb-core-ui-bin", default=None)
    parser.add_argument("--focus", default="", help="optional subsystem/area to concentrate on")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    focus = f"Concentrate on: {args.focus}\n" if args.focus else "Scan the whole codebase.\n"
    try:
        need = {"claude session connects", "kb-core-ui MCP server"}
        with common.Task("anomaly-scan", repo, args.kb_core_ui_bin, need, args.skip_preflight) as t:
            findings = common.extract_json(t.ask(PROMPT.format(focus=focus)))

        if not isinstance(findings, list):
            print(f"[anomaly-scan] expected a JSON array, got {type(findings)}", file=sys.stderr)
            return 2

        print("\n=== Anomaly scan ===")
        if not findings:
            print("No anomalies found.")
            return 0
        findings = sorted(findings, key=lambda f: SEV_ORDER.get(f.get("severity", "low"), 2))
        print(f"{len(findings)} anomaly(ies):\n")
        for f in findings:
            print(f"{SEV_MARK.get(f.get('severity','low'),'[LOW ]')} {f.get('category','?'):<22} {f.get('location','?')}")
            print(f"       {f.get('summary','')}")
            if f.get("evidence"):
                print(f"       evidence: {f['evidence']}")
            if f.get("suggested_fix"):
                print(f"       fix: {f['suggested_fix']}")
            print()
        return 1 if any(f.get("severity") == "high" for f in findings) else 0

    except RuntimeError as e:
        print(f"[anomaly-scan] error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
