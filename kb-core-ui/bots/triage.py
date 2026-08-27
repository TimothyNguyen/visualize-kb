#!/usr/bin/env python3
"""Support Triage bot — correlate a GitHub issue to the code and suggest fixes.

Pulls a GitHub issue (title, body, comments), then uses the graph and memory
to locate the code most likely responsible and suggest concrete fixes with
file:line references. Prints a triage brief; with --comment it posts the
brief back on the issue.

Data sources: GitHub issues/PRs are supported now. Chat platforms
(Intercom) are a planned source — see bots/README.md; Intercom needs to be
authorized before it can be wired in, so it's intentionally not a source
here yet.

Usage:
    kb-core-ui bot triage <issue-number> [--repo PATH] [--comment]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import common

PROMPT = """\
Triage this GitHub issue against the codebase. Use kb-core-ui's MCP tools:
search_symbol / get_symbol / get_callers / get_callees / get_file_slice to
find the code most likely involved, and memory_search for any relevant
rules or past lessons (a similar bug may already be a stored lesson).

Issue #{number}: {title}

{body}

Respond with ONLY a fenced ```json block:
{{
  "summary": "<what the issue is really about, 1-2 sentences>",
  "likely_causes": [ {{"location": "<file:line or symbol>",
                       "why": "<why this code is the likely cause, grounded
                                in what the graph shows>"}} ],
  "suggested_fixes": [ "<concrete fix with reference>" ],
  "related_memory": [ "<title of a relevant stored rule/lesson, if any>" ],
  "confidence": "high"|"medium"|"low"
}}
Only assert a cause you verified via the tools. If the issue is too vague to
locate in code, say so in the summary and give an empty likely_causes list.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("issue", type=int, help="GitHub issue number")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--kb-core-ui-bin", default=None)
    parser.add_argument("--comment", action="store_true", help="post the triage brief as an issue comment")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        # gh auth is required here (we read an issue and maybe comment).
        need = {"gh authenticated", "claude session connects", "kb-core-ui MCP server"}

        meta_raw = common.gh(["issue", "view", str(args.issue), "--json", "title,body"], cwd=repo)
        meta = json.loads(meta_raw)

        with common.Task("triage", repo, args.kb_core_ui_bin, need, args.skip_preflight) as t:
            prompt = PROMPT.format(number=args.issue, title=meta.get("title", ""), body=meta.get("body") or "(no body)")
            brief = common.extract_json(t.ask(prompt))

        text = render(args.issue, brief)
        print(text)

        if args.comment:
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
                f.write(text)
                body_file = f.name
            common.gh(["issue", "comment", str(args.issue), "--body-file", body_file], cwd=repo)
            os.unlink(body_file)
            print(f"\n[triage] posted a comment on issue #{args.issue}", file=sys.stderr)
        return 0

    except RuntimeError as e:
        print(f"[triage] error: {e}", file=sys.stderr)
        return 2


def render(number: int, b: dict) -> str:
    lines = [f"## 🤖 kb-core-ui triage — issue #{number}", "", b.get("summary", ""), ""]
    lines.append(f"**Confidence:** {b.get('confidence','?')}")
    lines.append("")
    lines.append("### Likely causes")
    causes = b.get("likely_causes") or []
    if not causes:
        lines.append("- could not localize this in code (issue may be too vague)")
    for c in causes:
        lines.append(f"- `{c.get('location','?')}` — {c.get('why','')}")
    lines.append("")
    lines.append("### Suggested fixes")
    for fix in b.get("suggested_fixes") or ["- (none)"]:
        lines.append(f"- {fix}")
    rel = b.get("related_memory") or []
    if rel:
        lines.append("")
        lines.append("### Related memory")
        for r in rel:
            lines.append(f"- {r}")
    lines.append("")
    lines.append("_Correlated using the kb-core-ui code graph + vector memory._")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
