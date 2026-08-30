#!/usr/bin/env python3
"""Shared toolkit for kb-core-ui's AI bots.

Every AI bot follows the same shape: ensure the graph is indexed, hand a
headless `claude` session kb-core-ui's MCP server (so the model searches the
code graph and vector memory instead of reading whole files), run a
task-specific prompt, and parse structured output. That machinery lives
here so each bot stays a thin, task-specific script — and so there's one
place to fix when the flow changes.

Stdlib only: bots run both on a dev machine and in CI, so nothing here may
need `pip install`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

# The MCP tools a bot's claude session is allowed to use: the whole graph
# surface plus the vector memory. memory_search lets a bot pull the
# codebase's rules/lessons; memory_add lets it persist new ones.
KB_CORE_UI_TOOLS = [
    "mcp__kb-core-ui__search_symbol",
    "mcp__kb-core-ui__get_symbol",
    "mcp__kb-core-ui__get_file_symbols",
    "mcp__kb-core-ui__get_callers",
    "mcp__kb-core-ui__get_callees",
    "mcp__kb-core-ui__get_file_slice",
    "mcp__kb-core-ui__get_tree",
    "mcp__kb-core-ui__get_stats",
    "mcp__kb-core-ui__memory_search",
    "mcp__kb-core-ui__memory_add",
]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def gh(args: list[str], cwd: Path) -> str:
    result = run(["gh"] + args, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def find_kb_core_ui_bin(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    # Use this interpreter's installed Python console script, not a stale Go
    # build in the checkout or on PATH. --kb-core-ui-bin opts into legacy Go.
    name = "kb-core-ui.exe" if os.name == "nt" else "kb-core-ui"
    local = Path(sysconfig.get_path("scripts")) / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    raise RuntimeError(
        "no Python kb-core-ui entry point found - install with "
        "`python -m pip install -e ./python` from kb-core-ui/ using this "
        "interpreter, or pass --kb-core-ui-bin for an explicit runtime"
    )


def ensure_indexed(kb_core_ui_bin: str, repo: Path) -> None:
    result = run([kb_core_ui_bin, "parse", str(repo)], cwd=repo)
    if result.returncode != 0:
        raise RuntimeError(f"kb-core-ui parse failed:\n{result.stderr}")


def build_mcp_config(kb_core_ui_bin: str, repo: Path, tmpdir: Path) -> Path:
    config = {
        "mcpServers": {
            "kb-core-ui": {"command": kb_core_ui_bin, "args": ["mcp", str(repo)]}
        }
    }
    path = tmpdir / "mcp-config.json"
    path.write_text(json.dumps(config))
    return path


def run_claude(prompt: str, mcp_config: Path, extra_tools: list[str] | None = None) -> str:
    """Run a headless claude session with kb-core-ui's MCP tools and return the
    model's final text. Raises RuntimeError with a clear message on any
    failure (bad exit, auth error, malformed envelope)."""
    tools = list(KB_CORE_UI_TOOLS)
    if extra_tools:
        tools += extra_tools
    cmd = [
        "claude", "-p", prompt,
        "--mcp-config", str(mcp_config),
        "--strict-mcp-config",
        "--output-format", "json",
        "--allowedTools", ",".join(tools),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"claude invocation failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}")
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"claude did not return a valid JSON envelope: {e}\nraw: {result.stdout[:2000]}")
    if envelope.get("is_error"):
        raise RuntimeError(f"claude returned an error: {envelope.get('result')}")
    return envelope.get("result", "")


def extract_json(claude_output: str):
    """Pull the first fenced ```json block (or the whole thing) and parse it.
    Bots ask the model to answer with a single JSON block."""
    match = re.search(r"```json\s*(.*?)\s*```", claude_output, re.DOTALL)
    text = match.group(1) if match else claude_output.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"could not parse JSON from claude's response: {e}\nraw: {claude_output[:2000]}")


def preflight_or_exit(repo: Path, kb_core_ui_bin: str | None, need: set[str], label: str) -> None:
    """Run shared preflight checks and exit(2) with a clear message if a link
    this bot needs is broken — instead of failing deep inside with a raw 401.
    `need` is the set of check names that must pass (see preflight.py)."""
    import preflight  # local module, same dir

    checks = preflight.run_checks(repo, kb_core_ui_bin, include_mcp=True)
    blocking = [c for c in checks if not c.ok and c.name in need]
    if blocking:
        print(f"[{label}] preflight failed — not starting:", file=sys.stderr)
        for c in blocking:
            print(f"  ✗ {c.name}: {c.detail}", file=sys.stderr)
            if c.fix:
                print(f"      fix: {c.fix}", file=sys.stderr)
        print("  (run `kb-core-ui bot doctor` for the full report)", file=sys.stderr)
        sys.exit(2)


class Task:
    """Convenience context for a bot run: locates the binary, preflights,
    indexes, and yields a ready-to-use claude runner bound to an MCP config.

    Usage:
        with Task("commit-check", repo, kb_core_ui_bin, need={...}) as t:
            text = t.ask(prompt)
    """

    def __init__(self, label: str, repo: Path, kb_core_ui_bin: str | None,
                 need: set[str], skip_preflight: bool = False):
        self.label = label
        self.repo = repo
        self.kb_core_ui_bin = find_kb_core_ui_bin(kb_core_ui_bin)
        self._need = need
        self._skip_preflight = skip_preflight
        self._tmp = None
        self._mcp_config = None

    def __enter__(self) -> "Task":
        if not self._skip_preflight:
            preflight_or_exit(self.repo, self.kb_core_ui_bin, self._need, self.label)
        print(f"[{self.label}] indexing {self.repo}...", file=sys.stderr)
        ensure_indexed(self.kb_core_ui_bin, self.repo)
        self._tmp = tempfile.TemporaryDirectory()
        self._mcp_config = build_mcp_config(self.kb_core_ui_bin, self.repo, Path(self._tmp.name))
        return self

    def ask(self, prompt: str) -> str:
        print(f"[{self.label}] running claude (this calls the model, may take a minute)...", file=sys.stderr)
        return run_claude(prompt, self._mcp_config)

    def __exit__(self, *exc):
        if self._tmp:
            self._tmp.cleanup()
        return False
