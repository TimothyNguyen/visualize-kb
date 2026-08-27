from __future__ import annotations

import os
import shutil
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
}

GO_ENGINE = EngineConfig(
    name="go",
    resolve_bin=resolve_go_binary,
    cli_templates=GO_CLI_TEMPLATES,
    serve_template=["{bin}", "serve", "{repo}", "--db", "{db}", "--port", "{port}", "--open=false"],
    mcp_template=["{bin}", "mcp", "{repo}", "--db", "{db}"],
)

# T5+ (Python port) adds ENGINES["python"] = EngineConfig(...) here — zero
# changes to runner.py/canonical.py/diff.py/operations.py required.
ENGINES: dict[str, EngineConfig] = {"go": GO_ENGINE}


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
