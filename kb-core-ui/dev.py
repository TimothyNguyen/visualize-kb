"""Portable launcher for kb-core-ui frontend or backend+served UI.

Use this from repo root after installing each package into its own environment:

    .venv-core/Scripts/python -m pip install -e ./kb-core   # Windows
    .venv-core/bin/python -m pip install -e ./kb-core       # macOS/Linux
    .venv-ui/Scripts/python -m pip install -e ./kb-core-ui/python
    .venv-ui/bin/python -m pip install -e ./kb-core-ui/python

Then run one of:

    python kb-core-ui/dev.py frontend <repo>
    python kb-core-ui/dev.py serve <repo>

This avoids shell-specific Windows/MSYS2 path handling by letting Python spawn
native subprocesses directly.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
WEB_DIR = APP_ROOT / "web"
PUBLIC_GRAPH = WEB_DIR / "public" / "kb-core-out" / "graph.json"
PUBLIC_OVERVIEW = WEB_DIR / "public" / "kb-core-out" / "graph-overview.json"
OVERVIEW_NODE_LIMIT = 500


def _require_module(name: str) -> None:
    try:
        __import__(name)
    except ImportError as exc:
        raise SystemExit(f"{name} is not installed in this environment.") from exc


def _npm_executable() -> str:
    if sys.platform == "win32":
        for candidate in ("npm.cmd", "npm.exe", "npm"):
            path = shutil.which(candidate)
            if path:
                return path
    return shutil.which("npm") or "npm"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    try:
        subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"missing executable: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


def _repo_root(path: str) -> Path:
    repo = Path(path).expanduser().resolve()
    if not repo.is_dir():
        raise SystemExit(f"repo path is not a directory: {repo}")
    return repo


def _extract_graph(repo: Path) -> Path:
    # Prefer the active interpreter so a global kb-core cannot shadow its venv.
    kb_core_python = os.environ.get("KB_CORE_PYTHON")
    if kb_core_python:
        _run(
            [kb_core_python, "-m", "kb_core", "extract", str(repo), "--code-only"],
            cwd=APP_ROOT,
        )
    else:
        try:
            __import__("kb_core")
        except ImportError:
            kb_core_bin = shutil.which("kb-core")
            if not kb_core_bin:
                _require_module("kb_core")
            _run([kb_core_bin, "extract", str(repo), "--code-only"], cwd=APP_ROOT)
        else:
            _run(
                [sys.executable, "-m", "kb_core", "extract", str(repo), "--code-only"],
                cwd=APP_ROOT,
            )
    graph = repo / "kb-core-out" / "graph.json"
    if not graph.exists():
        raise SystemExit(f"graph not found after extract: {graph}")
    PUBLIC_GRAPH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(graph, PUBLIC_GRAPH)
    _write_overview(graph)
    return graph


def _write_overview(graph: Path) -> None:
    """Write small high-connectivity graph used for fast first paint."""
    data = json.loads(graph.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or []
    links = data.get("links", data.get("edges")) or []
    degree: dict[str, int] = {}
    for link in links:
        for endpoint in (link.get("source"), link.get("target")):
            if endpoint is not None:
                degree[str(endpoint)] = degree.get(str(endpoint), 0) + 1
    ranked = sorted(
        nodes,
        key=lambda node: (-degree.get(str(node.get("id")), 0), str(node.get("id"))),
    )[:OVERVIEW_NODE_LIMIT]
    ids = {str(node.get("id")) for node in ranked}
    overview = {
        "nodes": ranked,
        "links": [
            link
            for link in links
            if str(link.get("source")) in ids and str(link.get("target")) in ids
        ],
        "overview": True,
        "total_nodes": len(nodes),
        "total_links": len(links),
    }
    PUBLIC_OVERVIEW.write_text(json.dumps(overview, separators=(",", ":")), encoding="utf-8")


def _ensure_web_deps() -> None:
    if not (WEB_DIR / "node_modules").exists():
        _run([_npm_executable(), "ci"], cwd=WEB_DIR)


def _frontend(repo: Path) -> None:
    _extract_graph(repo)
    _ensure_web_deps()
    _run([_npm_executable(), "run", "dev"], cwd=WEB_DIR)


def _served_ui(repo: Path) -> None:
    _extract_graph(repo)
    _ensure_web_deps()
    _run([_npm_executable(), "run", "build"], cwd=WEB_DIR)
    _require_module("kb_core_ui")
    _run(
        [
            sys.executable,
            "-m",
            "kb_core_ui",
            "serve",
            str(repo),
            "--web-dir",
            str(WEB_DIR / "dist"),
            "--host",
            os.environ.get("KB_CORE_UI_HOST", "127.0.0.1"),
        ],
        cwd=APP_ROOT,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dev.py",
        description="Run kb-core-ui frontend or backend+served UI.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    for name, help_text in (
        ("frontend", "Run Vite dev server after copying graph.json"),
        ("serve", "Build web/dist and run kb-core-ui serve"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("repo", nargs="?", default=".", help="repo to index")

    args = parser.parse_args(argv)
    repo = _repo_root(args.repo)

    if args.mode == "frontend":
        _frontend(repo)
    else:
        _served_ui(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
