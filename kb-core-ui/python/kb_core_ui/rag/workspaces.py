"""Persistent workspace, source, and ingestion-run lifecycle model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

WORKSPACE_SCHEMA_VERSION = "kb-core.workspaces.v1"

WORKSPACE_ACTIVE = "active"
WORKSPACE_DELETING = "deleting"

SOURCE_PENDING = "pending"
SOURCE_INGESTING = "ingesting"
SOURCE_READY = "ready"
SOURCE_FAILED = "failed"
SOURCE_DELETING = "deleting"

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

SOURCE_KINDS = frozenset(
    {"local_repo", "github_repo", "document_set", "document_url"}
)
_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_RUN_TRANSITIONS = {
    RUN_QUEUED: frozenset({RUN_RUNNING, RUN_CANCELLED}),
    RUN_RUNNING: frozenset({RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED}),
    RUN_SUCCEEDED: frozenset(),
    RUN_FAILED: frozenset(),
    RUN_CANCELLED: frozenset(),
}


class WorkspaceError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _valid_id(value: str, label: str) -> str:
    if not _ID.fullmatch(value):
        raise WorkspaceError(
            f"{label} must start with a lowercase letter and contain only lowercase letters, digits, or hyphens (max 63)"
        )
    return value


def workspace_graph_name(workspace_id: str) -> str:
    return "kb_workspace_" + _valid_id(workspace_id, "workspace id").replace("-", "_")


@dataclass
class Source:
    id: str
    workspace_id: str
    kind: str
    uri: str
    ref: str = ""
    status: str = SOURCE_PENDING
    content_hash: str = ""
    extractor_version: str = ""
    active_version: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_json_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "Source":
        return cls(**value)


@dataclass
class IngestionRun:
    id: str
    workspace_id: str
    source_id: str
    status: str = RUN_QUEUED
    error: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str = ""
    finished_at: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return dict(vars(self))

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "IngestionRun":
        return cls(**value)


@dataclass
class Workspace:
    id: str
    name: str
    graph_name: str
    status: str = WORKSPACE_ACTIVE
    sources: dict[str, Source] = field(default_factory=dict)
    runs: dict[str, IngestionRun] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "graph_name": self.graph_name,
            "status": self.status,
            "sources": {key: value.to_json_dict() for key, value in sorted(self.sources.items())},
            "runs": {key: value.to_json_dict() for key, value in sorted(self.runs.items())},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_json_dict(cls, value: Mapping[str, Any]) -> "Workspace":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            graph_name=str(value["graph_name"]),
            status=str(value.get("status", WORKSPACE_ACTIVE)),
            sources={
                key: Source.from_json_dict(source)
                for key, source in value.get("sources", {}).items()
            },
            runs={
                key: IngestionRun.from_json_dict(run)
                for key, run in value.get("runs", {}).items()
            },
            created_at=str(value.get("created_at", "")),
            updated_at=str(value.get("updated_at", "")),
        )


class WorkspaceRegistry:
    def __init__(self, path: str):
        self.path = Path(path)
        self.workspaces: dict[str, Workspace] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError(f"cannot read workspace registry {self.path}: {exc}") from None
        if raw.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
            raise WorkspaceError(
                f"unsupported workspace registry schema {raw.get('schema_version')!r}"
            )
        self.workspaces = {
            key: Workspace.from_json_dict(value)
            for key, value in raw.get("workspaces", {}).items()
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspaces": {
                key: value.to_json_dict() for key, value in sorted(self.workspaces.items())
            },
        }
        temp_path = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            temp_path.replace(self.path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise WorkspaceError(f"cannot write workspace registry {self.path}: {exc}") from None

    def list(self) -> list[Workspace]:
        return [self.workspaces[key] for key in sorted(self.workspaces)]

    def get(self, workspace_id: str) -> Workspace:
        workspace = self.workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(f"workspace {workspace_id!r} does not exist")
        return workspace

    def create(self, workspace_id: str, name: str) -> Workspace:
        _valid_id(workspace_id, "workspace id")
        if not name.strip():
            raise WorkspaceError("workspace name is required")
        if workspace_id in self.workspaces:
            raise WorkspaceError(f"workspace {workspace_id!r} already exists")
        workspace = Workspace(
            id=workspace_id, name=name.strip(), graph_name=workspace_graph_name(workspace_id)
        )
        self.workspaces[workspace_id] = workspace
        self._save()
        return workspace

    def mark_deleting(self, workspace_id: str) -> Workspace:
        workspace = self.get(workspace_id)
        workspace.status = WORKSPACE_DELETING
        workspace.updated_at = _now()
        self._save()
        return workspace

    def add_source(
        self,
        workspace_id: str,
        source_id: str,
        kind: str,
        uri: str,
        ref: str = "",
    ) -> Source:
        workspace = self.get(workspace_id)
        if workspace.status != WORKSPACE_ACTIVE:
            raise WorkspaceError(f"workspace {workspace_id!r} is not active")
        _valid_id(source_id, "source id")
        if kind not in SOURCE_KINDS:
            raise WorkspaceError(f"unsupported source kind {kind!r}")
        if not uri.strip():
            raise WorkspaceError("source uri is required")
        if source_id in workspace.sources:
            raise WorkspaceError(
                f"source {source_id!r} already exists in workspace {workspace_id!r}"
            )
        source = Source(
            id=source_id,
            workspace_id=workspace_id,
            kind=kind,
            uri=uri.strip(),
            ref=ref.strip(),
        )
        workspace.sources[source_id] = source
        workspace.updated_at = _now()
        self._save()
        return source

    def mark_source_deleting(self, workspace_id: str, source_id: str) -> Source:
        source = self._source(workspace_id, source_id)
        if source.status == SOURCE_INGESTING:
            raise WorkspaceError("cannot delete source while ingestion is running")
        source.status = SOURCE_DELETING
        source.updated_at = _now()
        self._save()
        return source

    def queue_run(self, workspace_id: str, source_id: str) -> IngestionRun:
        workspace = self.get(workspace_id)
        source = self._source(workspace_id, source_id)
        if workspace.status != WORKSPACE_ACTIVE or source.status == SOURCE_DELETING:
            raise WorkspaceError("workspace and source must be active before ingestion")
        if any(
            run.source_id == source_id and run.status in {RUN_QUEUED, RUN_RUNNING}
            for run in workspace.runs.values()
        ):
            raise WorkspaceError(f"source {source_id!r} already has an active ingestion run")
        run = IngestionRun(
            id="run_" + uuid4().hex,
            workspace_id=workspace_id,
            source_id=source_id,
        )
        workspace.runs[run.id] = run
        workspace.updated_at = _now()
        self._save()
        return run

    def transition_run(self, workspace_id: str, run_id: str, status: str, error: str = "") -> IngestionRun:
        workspace = self.get(workspace_id)
        run = workspace.runs.get(run_id)
        if run is None:
            raise WorkspaceError(f"run {run_id!r} does not exist in workspace {workspace_id!r}")
        if status not in _RUN_TRANSITIONS[run.status]:
            raise WorkspaceError(f"cannot transition run from {run.status!r} to {status!r}")
        source = self._source(workspace_id, run.source_id)
        now = _now()
        run.status = status
        if status == RUN_RUNNING:
            run.started_at = now
            source.status = SOURCE_INGESTING
        elif status == RUN_SUCCEEDED:
            run.finished_at = now
            source.status = SOURCE_READY
        elif status == RUN_FAILED:
            run.finished_at = now
            run.error = error
            source.status = SOURCE_FAILED
        elif status == RUN_CANCELLED:
            run.finished_at = now
            source.status = SOURCE_READY if source.active_version else SOURCE_PENDING
        source.updated_at = now
        workspace.updated_at = now
        self._save()
        return run

    def _source(self, workspace_id: str, source_id: str) -> Source:
        workspace = self.get(workspace_id)
        source = workspace.sources.get(source_id)
        if source is None:
            raise WorkspaceError(
                f"source {source_id!r} does not exist in workspace {workspace_id!r}"
            )
        return source
