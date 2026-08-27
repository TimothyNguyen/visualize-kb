#!/usr/bin/env python3
"""Feature Verdict bot — plan a feature against the actual codebase.

Given a proposed feature in plain English, it uses the graph and memory to
give a planning verdict BEFORE any code is written: which of the codebase's
rules the feature might break, which existing code it should reuse, the more
optimal design options, a concise PRD, and the tests needed so current
behavior doesn't break. Prints a structured markdown brief.

Usage:
    kb-core-ui bot feature-verdict "<feature description>" [--repo PATH]
    kb-core-ui bot feature-verdict --from-file spec.md [--repo PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common

PROMPT = """\
A developer is proposing this feature:

\"\"\"{feature}\"\"\"

Give a planning verdict for it, grounded in THIS codebase — do not answer
generically. Use kb-core-ui's MCP tools: memory_search to load the project's
primary rules, business logic, and past lessons; get_tree/get_stats/
search_symbol/get_symbol/get_callers/get_callees to find the code this
feature would touch and what already exists that it should reuse.

Respond with ONLY a fenced ```json block:
{{
  "summary": "<2-3 sentence read on the feature in this codebase's context>",
  "breaks_rules": [ {{"rule": "<the rule, from memory or observed convention>",
                      "risk": "<how this feature might violate it>"}} ],
  "reuse": [ {{"existing": "<symbol/file that already does part of this>",
              "why": "<what to reuse instead of rewriting>"}} ],
  "options": [ {{"name": "<option name>", "approach": "<1-2 sentences>",
                "tradeoffs": "<pros/cons>", "recommended": <true|false>}} ],
  "prd": "<a concise PRD: goal, scope, out-of-scope, acceptance criteria>",
  "tests_to_protect_current_behavior": [
      "<specific test that should exist/pass so this change doesn't break X>" ]
}}
Base every claim on something you verified via the tools; prefer fewer,
grounded points over speculation.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("feature", nargs="?", default="", help="the feature description")
    parser.add_argument("--from-file", default=None, help="read the feature description from a file ('-' for stdin)")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--kb-core-ui-bin", default=None)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    feature = args.feature
    if args.from_file:
        feature = (sys.stdin.read() if args.from_file == "-" else Path(args.from_file).read_text())
    if not feature.strip():
        print("[feature-verdict] provide a feature description (arg or --from-file)", file=sys.stderr)
        return 2

    repo = Path(args.repo).resolve()
    try:
        need = {"claude session connects", "kb-core-ui MCP server"}
        with common.Task("feature-verdict", repo, args.kb_core_ui_bin, need, args.skip_preflight) as t:
            v = common.extract_json(t.ask(PROMPT.format(feature=feature.strip())))
        render(v)
        return 0
    except RuntimeError as e:
        print(f"[feature-verdict] error: {e}", file=sys.stderr)
        return 2


def render(v: dict) -> None:
    def section(title):
        print(f"\n## {title}")

    print("\n=== Feature verdict ===")
    if v.get("summary"):
        print(v["summary"])

    section("Rules this might break")
    breaks = v.get("breaks_rules") or []
    if not breaks:
        print("- none identified")
    for b in breaks:
        print(f"- {b.get('rule','?')}\n    risk: {b.get('risk','')}")

    section("Reuse instead of rewriting")
    reuse = v.get("reuse") or []
    if not reuse:
        print("- nothing existing found to reuse")
    for r in reuse:
        print(f"- {r.get('existing','?')} — {r.get('why','')}")

    section("Options")
    for o in v.get("options") or []:
        star = " (recommended)" if o.get("recommended") else ""
        print(f"- {o.get('name','?')}{star}: {o.get('approach','')}")
        if o.get("tradeoffs"):
            print(f"    tradeoffs: {o['tradeoffs']}")

    section("PRD")
    print(v.get("prd", "(none)"))

    section("Tests to protect current behavior")
    for tst in v.get("tests_to_protect_current_behavior") or []:
        print(f"- {tst}")


if __name__ == "__main__":
    sys.exit(main())
