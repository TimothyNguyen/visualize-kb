#!/usr/bin/env python3
"""Test Writer bot — generate test cases for a function/file using the graph.

Point it at a symbol name or file. It uses the graph to read the target's
signature, callers, and callees (so the tests exercise real usage and
edge cases, not guesses), then proposes test cases. By default it prints
them; pass --write to save to a file next to the target.

Usage:
    kb-core-ui bot test-writer <symbol-or-file> [--repo PATH] [--write]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import common

PROMPT = """\
Write test cases for the target below. First use the kb-core-ui MCP tools:
search_symbol / get_symbol to read its exact signature, params and returns;
get_callees to see what it depends on; get_callers to see how it's really
used (cover those real usage patterns and their edge cases). Call
memory_search for any testing conventions or rules this project has.

Target: {target}

Match the project's existing test style and framework (inspect a sibling
test file via get_file_symbols/get_file_slice to learn it). Cover: the
happy path, boundary/edge inputs, and error paths. Do NOT invent APIs —
only call functions the graph confirms exist.

Respond with ONLY a fenced ```json block:
{{"language": "<go|typescript|python|...>",
  "suggested_path": "<where this test file should live>",
  "test_code": "<the complete test file content>",
  "notes": "<what you covered and any gaps you couldn't cover>"}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="symbol name (e.g. BuildFlat) or file path to write tests for")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--kb-core-ui-bin", default=None)
    parser.add_argument("--write", action="store_true", help="write the test file to suggested_path instead of printing")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        need = {"claude session connects", "kb-core-ui MCP server"}
        with common.Task("test-writer", repo, args.kb_core_ui_bin, need, args.skip_preflight) as t:
            result = common.extract_json(t.ask(PROMPT.format(target=args.target)))

        code = result.get("test_code", "")
        path = result.get("suggested_path", "")
        if not code:
            print("[test-writer] the model returned no test code.", file=sys.stderr)
            return 2

        if args.write and path:
            # Never overwrite an existing file — writing tests should never
            # clobber real ones. Refuse and print instead.
            dest = (repo / path).resolve()
            if not str(dest).startswith(str(repo)):
                print(f"[test-writer] refusing to write outside the repo: {path}", file=sys.stderr)
                return 2
            if dest.exists():
                print(f"[test-writer] {path} already exists — not overwriting. Printing instead:\n", file=sys.stderr)
                print(code)
                return 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(code)
            print(f"[test-writer] wrote {path}")
        else:
            print(f"# Suggested path: {path}\n# Language: {result.get('language','?')}")
            if result.get("notes"):
                print(f"# Notes: {result['notes']}\n")
            print(code)
        return 0

    except RuntimeError as e:
        print(f"[test-writer] error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
