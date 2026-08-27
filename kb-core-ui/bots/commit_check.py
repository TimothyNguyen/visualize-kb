#!/usr/bin/env python3
"""Commit Check bot — review a single commit's diff for problems.

Same review dimensions as the PR bot, but at commit granularity: run it on
HEAD after committing (or on a specific ref) to catch breaking changes,
quality issues, duplication, unnecessary rewrites, pattern mismatches, and
cross-boundary contract ("hallucinated") mismatches before you push. Prints
a report; exits non-zero if any high-severity issue is found (so it can gate
a pre-push hook or CI).

Usage:
    kb-core-ui bot commit-check [<ref>] [--repo PATH]
    (ref defaults to HEAD)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common

CRITERIA = """\
Review this single commit's diff. Use the kb-core-ui MCP tools to check
claims against the actual codebase, and memory_search to learn the
project's rules and past lessons before judging. For each issue, classify
it as one of:

- breaking-change: changes an existing function/route/type contract in a
  way that could break callers (use get_callers to check who's affected).
- quality: unclear naming, missing error handling at a real boundary, dead
  code, obviously wrong logic.
- duplication: adds something that already exists (use search_symbol to
  confirm before flagging).
- unnecessary-rewrite: reimplements/restructures code that didn't need to
  change for this commit's purpose.
- pattern-mismatch: diverges from how the codebase does this kind of thing
  (call memory_search for the relevant rule; check similar existing code).
- hallucinated-contract: one side of a boundary assumes a shape/type the
  other side doesn't provide (the most important to check).

Respond with ONLY a fenced ```json block: an array of
{"severity": "high"|"medium"|"low", "category": <slug>, "file": <path>,
 "line": <int|null>, "summary": <one sentence>, "detail": <1-3 sentences>}.
Empty array [] if nothing is worth flagging.
"""

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
SEV_MARK = {"high": "[HIGH]", "medium": "[MED ]", "low": "[LOW ]"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ref", nargs="?", default="HEAD", help="commit ref to review (default HEAD)")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--kb-core-ui-bin", default=None)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()

    try:
        # `git show` includes the message + full diff for one commit.
        show = common.run(["git", "show", "--stat", "--patch", args.ref], cwd=repo)
        if show.returncode != 0:
            print(f"[commit-check] git show {args.ref} failed:\n{show.stderr}", file=sys.stderr)
            return 2
        diff = show.stdout
        if not diff.strip():
            print(f"[commit-check] {args.ref} has no diff to review.")
            return 0

        need = {"claude session connects", "kb-core-ui MCP server"}
        with common.Task("commit-check", repo, args.kb_core_ui_bin, need, args.skip_preflight) as t:
            prompt = f"{CRITERIA}\n\nCommit {args.ref}:\n```diff\n{diff}\n```"
            findings = common.extract_json(t.ask(prompt))

        if not isinstance(findings, list):
            print(f"[commit-check] expected a JSON array, got {type(findings)}", file=sys.stderr)
            return 2

        report(args.ref, findings)
        return 1 if any(f.get("severity") == "high" for f in findings) else 0

    except RuntimeError as e:
        print(f"[commit-check] error: {e}", file=sys.stderr)
        return 2


def report(ref: str, findings: list[dict]) -> None:
    print(f"\n=== Commit check: {ref} ===")
    if not findings:
        print("No issues found.")
        return
    findings = sorted(findings, key=lambda f: SEV_ORDER.get(f.get("severity", "low"), 2))
    print(f"{len(findings)} finding(s):\n")
    for f in findings:
        loc = f.get("file", "?")
        if f.get("line"):
            loc += f":{f['line']}"
        print(f"{SEV_MARK.get(f.get('severity','low'),'[LOW ]')} {f.get('category','?'):<22} {loc}")
        print(f"       {f.get('summary','')}")
        if f.get("detail"):
            print(f"       {f['detail']}")
        print()


if __name__ == "__main__":
    sys.exit(main())
