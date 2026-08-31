"""Fixture seeding for the local dev stack.

The compose entrypoint, the docs, and the harness all reach a seeded
workspace through this one function so the dev stack exercises the same
manager boundary a user drives from the CLI or the browser.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class SeedError(ValueError):
    pass


@dataclass(frozen=True)
class SeedSource:
    id: str
    kind: str
    uri: str
    ref: str = ""


@dataclass(frozen=True)
class SeedFixture:
    workspace_id: str
    workspace_name: str
    sources: tuple[SeedSource, ...]


def load_seed_fixture(path: str) -> SeedFixture:
    fixture_path = Path(path).expanduser()
    try:
        body = json.loads(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SeedError(f"seed fixture {path!r} is not readable: {exc}") from None
    except json.JSONDecodeError as exc:
        raise SeedError(f"seed fixture {path!r} is not valid JSON: {exc}") from None
    if not isinstance(body, Mapping):
        raise SeedError(f"seed fixture {path!r} must be a JSON object")

    workspace_id = str(body.get("workspace_id", "")).strip()
    if not workspace_id:
        raise SeedError("seed fixture needs a workspace_id")
    workspace_name = str(body.get("workspace_name", "")).strip() or workspace_id

    raw_sources = body.get("sources")
    if not isinstance(raw_sources, Sequence) or isinstance(raw_sources, str) or not raw_sources:
        raise SeedError("seed fixture needs at least one source")

    base = fixture_path.parent
    sources = []
    for entry in raw_sources:
        if not isinstance(entry, Mapping):
            raise SeedError("each seed source must be a JSON object")
        source_id = str(entry.get("id", "")).strip()
        kind = str(entry.get("kind", "")).strip()
        uri = str(entry.get("uri", "")).strip()
        if not source_id or not kind or not uri:
            raise SeedError("each seed source needs id, kind, and uri")
        sources.append(
            SeedSource(source_id, kind, str((base / uri).resolve()), str(entry.get("ref", "")).strip())
        )
    return SeedFixture(workspace_id, workspace_name, tuple(sources))


def seed_workspace(manager, fixture: SeedFixture, reset: bool = False) -> dict[str, Any]:
    existing = {workspace["id"]: workspace for workspace in manager.list_workspaces()}
    workspace = existing.get(fixture.workspace_id)

    was_reset = False
    if reset and workspace is not None:
        manager.delete_workspace(fixture.workspace_id)
        workspace, was_reset = None, True

    created = workspace is None
    if created:
        manager.create_workspace(fixture.workspace_id, fixture.workspace_name)
        known_sources: set[str] = set()
    else:
        known_sources = set(workspace.get("sources", {}))

    results = []
    for source in fixture.sources:
        added = source.id not in known_sources
        if added:
            manager.add_source(
                fixture.workspace_id, source.id, source.kind, source.uri, source.ref
            )
            run = manager.start_ingestion(fixture.workspace_id, source.id)
        else:
            run = manager.refresh_source(fixture.workspace_id, source.id)
        results.append(
            {
                "id": source.id,
                "kind": source.kind,
                "added": added,
                "run_id": str(run.get("id", "")),
                "status": str(run.get("status", "")),
                "error": str(run.get("error", "")),
            }
        )
    return {
        "workspace_id": fixture.workspace_id,
        "created": created,
        "reset": was_reset,
        "sources": results,
    }
