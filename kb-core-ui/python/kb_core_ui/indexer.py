"""Walks a repo, parses every supported file whose content hash changed, and
writes the result into a Store — the Python side of internal/indexer.

The walk reproduces filepath.WalkDir: entries per directory are visited in
lexical order and directories are descended into as they are reached, rather
than after all sibling files. That ordering decides symbol insert order,
which decides edge insert order.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass

from kb_core_ui.errors import IndexError_, KbError
from kb_core_ui.parser import language_for, parse_file
from kb_core_ui.store import Store

# Never worth descending into: VCS metadata, dependency trees, build output.
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build",
    ".next", "__pycache__", "venv", ".venv", "target",
    ".kb-core-ui",
}


@dataclass
class Result:
    files_scanned: int = 0
    files_changed: int = 0
    files_removed: int = 0


def content_hash(src: bytes) -> str:
    return hashlib.sha256(src).hexdigest()


def _walk(directory: str):
    with os.scandir(directory) as it:
        entries = sorted(it, key=lambda e: e.name)
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            # Descend immediately rather than after the sibling files, so a
            # directory's subtree lands between its lexical neighbours exactly
            # as filepath.WalkDir orders it.
            if entry.name not in SKIP_DIRS:
                yield from _walk(entry.path)
        else:
            yield entry.path


def index(root: str, store: Store) -> Result:
    """Parses changed/new files into store, prunes files gone from disk, and
    rebuilds the edge table once at the end — edge resolution needs the whole
    repo's symbols, so it can't be done per file."""
    res = Result()
    seen: set[str] = set()

    for path in _walk(root):
        if not language_for(path)[1]:
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        seen.add(rel)
        res.files_scanned += 1

        try:
            with open(path, "rb") as fh:
                src = fh.read()
        except OSError as exc:
            raise IndexError_(f"indexer: read {rel}: {exc.strerror}") from None
        file_hash = content_hash(src)

        prev_hash, known = store.file_hash(rel)
        if known and prev_hash == file_hash:
            continue

        try:
            fg = parse_file(rel, src)
        except KbError as exc:
            raise IndexError_(f"indexer: parse {rel}: {exc}") from None
        try:
            store.upsert_file(fg, file_hash)
        except (KbError, sqlite3.Error) as exc:
            raise IndexError_(f"indexer: store {rel}: {exc}") from None
        res.files_changed += 1

    for path in store.known_files():
        if path not in seen:
            store.remove_file(path)
            res.files_removed += 1

    if res.files_changed > 0 or res.files_removed > 0:
        store.rebuild_edges()

    return res
