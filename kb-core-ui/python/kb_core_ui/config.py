from __future__ import annotations

import os
from pathlib import Path

from kb_core_ui.errors import RepoPathError

DB_DIR_NAME = ".kb-core-ui"


def resolve_repo_path(args: list[str] | None) -> str:
    path = args[0] if args else "."
    if path == "":
        path = "."
    abs_path = os.path.abspath(path)
    try:
        info = os.stat(abs_path)
    except OSError as exc:
        raise RepoPathError(f"repo path {abs_path}: {exc.strerror}") from None
    if not os.path.isdir(abs_path):
        raise RepoPathError(f"repo path {abs_path} is not a directory")
    del info
    return abs_path


def default_db_path(repo_root: str) -> str:
    return str(Path(repo_root) / DB_DIR_NAME / "graph.db")


def memory_db_path(repo_root: str) -> str:
    # Deliberately a separate file from graph.db: the graph is derived from
    # source and rebuilt freely, memory is authored knowledge that must
    # survive re-indexing.
    return str(Path(repo_root) / DB_DIR_NAME / "memory.db")


def ensure_db_dir(repo_root: str) -> None:
    (Path(repo_root) / DB_DIR_NAME).mkdir(parents=True, exist_ok=True)
