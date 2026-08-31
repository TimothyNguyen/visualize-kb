"""Idempotent source reconciliation over versioned FalkorDB staging records."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from kb_core_ui.rag.contracts import GraphEnvelope
from kb_core_ui.rag.workspaces import RUN_FAILED, RUN_SUCCEEDED, WorkspaceRegistry


class ReconcileError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceManifest:
    source_id: str
    active_version: str
    content_hash: str
    extractor_version: str


@dataclass(frozen=True)
class StageCounts:
    nodes: int
    relationships: int
    chunks: int
    citations: int

    @classmethod
    def from_envelope(cls, envelope: GraphEnvelope) -> "StageCounts":
        return cls(
            nodes=len(envelope.nodes),
            relationships=len(envelope.relationships),
            chunks=len(envelope.chunks),
            citations=len(envelope.citations),
        )


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    version: str
    counts: StageCounts


class ReconcileAdapter(Protocol):
    def get_source_manifest(self, source_id: str) -> SourceManifest | None: ...

    def recover_source(self, source_id: str, active_version: str) -> None: ...

    def begin_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None: ...

    def stage_envelope(self, envelope: GraphEnvelope, version: str) -> None: ...

    def verify_source_stage(self, source_id: str, version: str) -> StageCounts: ...

    def publish_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None: ...

    def rollback_source_stage(self, source_id: str, version: str) -> None: ...


def source_version(envelope: GraphEnvelope) -> str:
    value = f"{envelope.schema_version}\0{envelope.extractor_version}\0{envelope.content_hash}"
    return "version_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class SourceReconciler:
    def __init__(self, adapter: ReconcileAdapter, registry: WorkspaceRegistry):
        self.adapter = adapter
        self.registry = registry

    def reconcile(
        self,
        workspace_id: str,
        source_id: str,
        run_id: str,
        envelope: GraphEnvelope,
    ) -> ReconcileResult:
        if envelope.workspace_id != workspace_id or envelope.source_id != source_id:
            raise ReconcileError("envelope scope does not match reconciliation scope")
        expected = StageCounts.from_envelope(envelope)
        manifest = self.adapter.get_source_manifest(source_id)
        if manifest and (
            manifest.content_hash == envelope.content_hash
            and manifest.extractor_version == envelope.extractor_version
        ):
            self.registry.publish_source(
                workspace_id,
                source_id,
                envelope.content_hash,
                envelope.extractor_version,
                manifest.active_version,
            )
            self.registry.transition_run(workspace_id, run_id, RUN_SUCCEEDED)
            return ReconcileResult("unchanged", manifest.active_version, expected)

        version = source_version(envelope)
        active_version = manifest.active_version if manifest else ""
        try:
            self.adapter.recover_source(source_id, active_version)
            self.adapter.begin_source_stage(
                source_id, version, envelope.content_hash, envelope.extractor_version
            )
            self.adapter.stage_envelope(envelope, version)
            actual = self.adapter.verify_source_stage(source_id, version)
            if actual != expected:
                raise ReconcileError(
                    f"staged record counts differ: expected {expected!r}, got {actual!r}"
                )
            self.adapter.publish_source_stage(
                source_id, version, envelope.content_hash, envelope.extractor_version
            )
            self.registry.publish_source(
                workspace_id,
                source_id,
                envelope.content_hash,
                envelope.extractor_version,
                version,
            )
            self.registry.transition_run(workspace_id, run_id, RUN_SUCCEEDED)
            return ReconcileResult("published", version, expected)
        except Exception as exc:
            try:
                self.adapter.rollback_source_stage(source_id, version)
            except Exception:
                pass
            self.registry.transition_run(workspace_id, run_id, RUN_FAILED, str(exc))
            if isinstance(exc, ReconcileError):
                raise
            raise ReconcileError(str(exc)) from exc
