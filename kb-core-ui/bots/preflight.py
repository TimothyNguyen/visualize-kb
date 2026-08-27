#!/usr/bin/env python3
"""Preflight checks shared by every kb-core-ui bot.

The single most important thing to verify before running any bot is the
literal question "can our app connect a Claude session from the terminal?"
— so this module checks that whole chain end to end and reports exactly
which link is broken, instead of letting a bot fail deep inside with a raw
401 dump.

Importable (bots call `run_checks()` before doing work) and runnable
directly (`python3 bots/preflight.py`, or `kb-core-ui bot doctor`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""  # actionable remediation when not ok


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 8)
    return Check(
        "python3",
        ok,
        f"Python {v.major}.{v.minor}.{v.micro}",
        "" if ok else "install Python 3.8+",
    )


def check_gh_installed() -> Check:
    path = shutil.which("gh")
    return Check(
        "gh installed",
        bool(path),
        path or "not found on PATH",
        "" if path else "install the GitHub CLI: https://cli.github.com",
    )


def check_gh_auth() -> Check:
    if not shutil.which("gh"):
        return Check("gh authenticated", False, "gh not installed", "install gh first")
    r = _run(["gh", "auth", "status"])
    # `gh auth status` also honors GH_TOKEN/GITHUB_TOKEN (how CI authenticates).
    token_env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    ok = r.returncode == 0 or bool(token_env)
    detail = "authenticated"
    if not ok:
        detail = (r.stderr or r.stdout or "not authenticated").strip().splitlines()[0]
    return Check(
        "gh authenticated",
        ok,
        detail,
        "" if ok else "run `gh auth login`, or set GH_TOKEN in CI",
    )


def check_claude_installed() -> Check:
    path = shutil.which("claude")
    return Check(
        "claude installed",
        bool(path),
        path or "not found on PATH",
        "" if path else "install Claude Code: npm install -g @anthropic-ai/claude-code",
    )


def check_claude_auth() -> Check:
    """The critical check: can we actually get a completion out of the
    claude CLI right now? This is the exact chain the bots depend on."""
    if not shutil.which("claude"):
        return Check("claude session connects", False, "claude not installed", "install claude first")

    r = _run(["claude", "-p", "reply with the single word: ok", "--output-format", "json"])
    detail = ""
    ok = False
    try:
        env = json.loads(r.stdout)
        if env.get("is_error"):
            detail = str(env.get("result", "")).strip()
            status = env.get("api_error_status")
            if status == 401:
                fix = "your claude login expired — run `claude` once interactively to re-login, or set ANTHROPIC_API_KEY"
            else:
                fix = "check the claude CLI: run `claude -p \"hi\"` yourself to see the error"
            return Check("claude session connects", False, detail or f"error {status}", fix)
        ok = True
        detail = "got a completion from the model"
    except (json.JSONDecodeError, TypeError):
        detail = (r.stderr or r.stdout or "no output").strip()[:200]
        return Check(
            "claude session connects",
            False,
            detail,
            "run `claude -p \"hi\"` yourself to diagnose",
        )
    return Check("claude session connects", ok, detail)


def check_claude_mcp(kb_core_ui_bin: str | None, repo: Path) -> Check:
    """Verify the app can hand its own MCP server to a claude session — the
    core 'search the graph instead of reading files' loop. Only meaningful
    if claude auth passed, but the MCP handshake itself is checked
    independently via the kb-core-ui binary."""
    if not kb_core_ui_bin:
        return Check("kb-core-ui MCP server", False, "no kb-core-ui binary located", "build with `go build -o kb-core-ui ./cmd/kb-core-ui`")

    # Drive the MCP server directly over stdio (no claude needed) to prove
    # the server half of the connection works regardless of model auth.
    init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"preflight","version":"1"}}}\n'
    listreq = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    try:
        proc = subprocess.run(
            [kb_core_ui_bin, "mcp", str(repo)],
            input=init + listreq,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return Check("kb-core-ui MCP server", False, "timed out", "check `kb-core-ui mcp .` runs")

    tools = []
    for line in proc.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2 and "result" in d:
            tools = [t["name"] for t in d["result"].get("tools", [])]
    ok = len(tools) >= 1
    return Check(
        "kb-core-ui MCP server",
        ok,
        f"exposes {len(tools)} tools" if ok else "did not list tools",
        "" if ok else "check `kb-core-ui mcp .` and that the repo is indexed",
    )


def find_kb_core_ui_bin(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    repo_root = Path(__file__).resolve().parent.parent
    local = repo_root / "kb-core-ui"
    if local.exists() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which("kb-core-ui")


def run_checks(repo: Path, kb_core_ui_bin: str | None = None, include_mcp: bool = True) -> list[Check]:
    bin_path = find_kb_core_ui_bin(kb_core_ui_bin)
    checks = [
        check_python(),
        check_gh_installed(),
        check_gh_auth(),
        check_claude_installed(),
        check_claude_auth(),
    ]
    if include_mcp:
        checks.append(check_claude_mcp(bin_path, repo))
    return checks


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify the bot orchestration chain is connectable.")
    parser.add_argument("--repo", default=".", help="repo to check the MCP server against")
    parser.add_argument("--kb-core-ui-bin", default=None)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    checks = run_checks(repo, args.kb_core_ui_bin)

    print("kb-core-ui orchestration preflight\n")
    all_ok = True
    for c in checks:
        mark = "✓" if c.ok else "✗"
        print(f"  {mark}  {c.name:<26} {c.detail}")
        if not c.ok:
            all_ok = False
            if c.fix:
                print(f"       ↳ fix: {c.fix}")

    print()
    if all_ok:
        print("All checks passed — bots can connect a Claude session and query the graph.")
        return 0
    print("Some checks failed — see the fixes above. Bots that need the failing")
    print("piece won't run until it's resolved.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
