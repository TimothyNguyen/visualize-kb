from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from harness.errors import EngineError


def resolve_go_binary(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("KB_CORE_UI_BIN")
    if env:
        return env
    # engines.py -> harness/harness/engines.py; parents[2] is the kb-core-ui
    # repo root, where `go build -o kb-core-ui ./cmd/kb-core-ui` drops its
    # binary (same convention as bots/common.py:find_kb_core_ui_bin).
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("kb-core-ui.exe", "kb-core-ui"):
        candidate = repo_root / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which("kb-core-ui")
    if found:
        return found
    raise EngineError(
        "no kb-core-ui binary found — build one with "
        "`go build -o kb-core-ui.exe ./cmd/kb-core-ui` (or kb-core-ui on non-Windows) "
        "from kb-core-ui/, or pass --go-bin / set $KB_CORE_UI_BIN"
    )


@dataclass(frozen=True)
class EngineConfig:
    name: str
    resolve_bin: Callable[[str | None], str]
    cli_templates: dict[str, list[str]]
    serve_template: list[str] | None = None
    mcp_template: list[str] | None = None
    ready_probe: str = "/api/stats"
    startup_timeout_s: float = 10.0


GO_CLI_TEMPLATES: dict[str, list[str]] = {
    "parse": ["{bin}", "parse", "{repo}", "--db", "{db}"],
    "memory_add": [
        "{bin}", "memory", "add", "--repo", "{repo}",
        "--kind", "{kind}", "--title", "{title}", "--text", "{text}",
    ],
    "memory_list": ["{bin}", "memory", "list", "--repo", "{repo}"],
    "memory_search": ["{bin}", "memory", "search", "{query}", "--repo", "{repo}", "--top", "{top}"],
    "memory_rm": ["{bin}", "memory", "rm", "{id}", "--repo", "{repo}"],
    # T1 surface templates: help text, usage errors, and exit codes.
    "help_root": ["{bin}", "--help"],
    "no_args": ["{bin}"],
    "help_parse": ["{bin}", "parse", "--help"],
    "help_memory": ["{bin}", "memory", "--help"],
    "unknown_command": ["{bin}", "bogus"],
    "parse_missing_repo": ["{bin}", "parse", "{repo}/does-not-exist", "--db", "{db}"],
    "parse_too_many_args": ["{bin}", "parse", "{repo}", "{repo}"],
    "memory_add_no_title": ["{bin}", "memory", "add", "--repo", "{repo}"],
    "memory_rm_absent": ["{bin}", "memory", "rm", "no-such-id", "--repo", "{repo}"],
}

# --web-dir is passed explicitly rather than left to each engine's
# auto-detection. web/dist is a build artifact, absent from a fresh checkout,
# so auto-detection would have both engines fall back to API-only and let the
# spa-serving fixture agree on two 404s without testing anything. See
# tests/webdir/README.md.
GO_ENGINE = EngineConfig(
    name="go",
    resolve_bin=resolve_go_binary,
    cli_templates=GO_CLI_TEMPLATES,
    serve_template=[
        "{bin}", "serve", "{repo}", "--db", "{db}", "--port", "{port}",
        "--web-dir", "{web_dir}", "--open=false",
    ],
    mcp_template=["{bin}", "mcp", "{repo}", "--db", "{db}"],
)

def resolve_python_binary(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("KB_CORE_UI_PY_BIN")
    if env:
        return env
    # The port is invoked as `python -m kb_core_ui`, so the "binary" is the
    # interpreter running the harness — the same venv the port is installed
    # into.
    return sys.executable


def _python_templates() -> dict[str, list[str]]:
    """Every Go CLI template with {bin} replaced by `{bin} -m kb_core_ui`, so
    the two engines stay argument-for-argument identical by construction."""
    return {
        name: ["{bin}", "-m", "kb_core_ui", *template[1:]]
        for name, template in GO_CLI_TEMPLATES.items()
    }


PYTHON_ENGINE = EngineConfig(
    name="python",
    resolve_bin=resolve_python_binary,
    cli_templates=_python_templates(),
    serve_template=[
        "{bin}", "-m", "kb_core_ui", "serve", "{repo}",
        "--db", "{db}", "--port", "{port}", "--web-dir", "{web_dir}", "--open=false",
    ],
    mcp_template=["{bin}", "-m", "kb_core_ui", "mcp", "{repo}", "--db", "{db}"],
)

ENGINES: dict[str, EngineConfig] = {"go": GO_ENGINE, "python": PYTHON_ENGINE}


def render_argv(template: list[str], values: dict[str, str]) -> list[str]:
    try:
        return [part.format_map(values) for part in template]
    except KeyError as exc:
        raise EngineError(f"unresolved placeholder {exc} in template {template!r}") from exc


@dataclass(frozen=True)
class ResolvedEngine:
    config: EngineConfig
    bin_path: str


def bin_override_for(args: object, engine_name: str) -> str | None:
    """Maps an engine name to its argparse override attribute, e.g. 'go' ->
    args.go_bin, 'python' -> args.python_bin (see cli.py's --go-bin/--python-bin)."""
    return getattr(args, f"{engine_name}_bin", None)


def get_engine(name: str, *, bin_override: str | None = None) -> ResolvedEngine:
    config = ENGINES.get(name)
    if config is None:
        raise EngineError(
            f"no engine registered for {name!r} (known: {sorted(ENGINES)}) — "
            "see SPEC.md T5-T11 for adding a python engine"
        )
    return ResolvedEngine(config=config, bin_path=config.resolve_bin(bin_override))
