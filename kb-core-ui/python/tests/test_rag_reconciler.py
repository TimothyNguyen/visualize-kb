from __future__ import annotations

from pathlib import Path

import pytest

from kb_core_ui.rag import (
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    ReconcileError,
    SourceManifest,
    SourceReconciler,
    StageCounts,
    WorkspaceRegistry,
    normalize_kb_core_graph,
)


class FakeReconcileAdapter:
    def __init__(self, manifest: SourceManifest | None = None, *, fail_stage: bool = False):
        self.manifest = manifest
        self.fail_stage = fail_stage
        self.calls: list[tuple] = []

    def get_source_manifest(self, source_id: str) -> SourceManifest | None:
        self.calls.append(("manifest", source_id))
        return self.manifest

    def recover_source(self, source_id: str, active_version: str) -> None:
        self.calls.append(("recover", source_id, active_version))

    def begin_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None:
        self.calls.append(("begin", source_id, version, content_hash, extractor_version))

    def stage_envelope(self, envelope, version: str) -> None:
        self.calls.append(("stage", envelope.source_id, version))
        if self.fail_stage:
            raise RuntimeError("injected stage failure")

    def verify_source_stage(self, source_id: str, version: str) -> StageCounts:
        self.calls.append(("verify", source_id, version))
        return StageCounts.from_envelope(ENVELOPE)

    def publish_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None:
        self.calls.append(("publish", source_id, version))
        self.manifest = SourceManifest(
            source_id=source_id,
            active_version=version,
            content_hash=content_hash,
            extractor_version=extractor_version,
        )

    def rollback_source_stage(self, source_id: str, version: str) -> None:
        self.calls.append(("rollback", source_id, version))


ENVELOPE = normalize_kb_core_graph(
    {
        "nodes": [
            {
                "id": "src/api.py:Api",
                "label": "Api",
                "source_location": "src/api.py:L1",
                "doc": "API entrypoint.",
            }
        ],
        "links": [],
    },
    workspace_id="alpha",
    source_id="repo",
).envelope


def running_registry(tmp_path: Path) -> tuple[WorkspaceRegistry, str]:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    registry.add_source("alpha", "repo", "local_repo", "fixture://repo")
    run = registry.queue_run("alpha", "repo")
    registry.transition_run("alpha", run.id, RUN_RUNNING)
    return registry, run.id


def test_unchanged_manifest_skips_writes_and_completes_run(tmp_path: Path) -> None:
    registry, run_id = running_registry(tmp_path)
    manifest = SourceManifest(
        source_id="repo",
        active_version="version-old",
        content_hash=ENVELOPE.content_hash,
        extractor_version=ENVELOPE.extractor_version,
    )
    adapter = FakeReconcileAdapter(manifest)

    result = SourceReconciler(adapter, registry).reconcile("alpha", "repo", run_id, ENVELOPE)

    assert result.status == "unchanged"
    assert result.version == "version-old"
    assert adapter.calls == [("manifest", "repo")]
    workspace = registry.get("alpha")
    assert workspace.runs[run_id].status == RUN_SUCCEEDED
    assert workspace.sources["repo"].content_hash == ENVELOPE.content_hash


def test_stage_failure_rolls_back_and_preserves_active_version(tmp_path: Path) -> None:
    registry, run_id = running_registry(tmp_path)
    adapter = FakeReconcileAdapter(
        SourceManifest("repo", "version-old", "old-hash", ENVELOPE.extractor_version),
        fail_stage=True,
    )

    with pytest.raises(ReconcileError, match="injected stage failure"):
        SourceReconciler(adapter, registry).reconcile("alpha", "repo", run_id, ENVELOPE)

    assert any(call[0] == "rollback" for call in adapter.calls)
    workspace = registry.get("alpha")
    assert workspace.runs[run_id].status == RUN_FAILED
    assert workspace.sources["repo"].active_version == ""


def test_retry_converges_to_deterministic_version(tmp_path: Path) -> None:
    registry, failed_run = running_registry(tmp_path)
    adapter = FakeReconcileAdapter(fail_stage=True)
    reconciler = SourceReconciler(adapter, registry)
    with pytest.raises(ReconcileError):
        reconciler.reconcile("alpha", "repo", failed_run, ENVELOPE)

    retry = registry.queue_run("alpha", "repo")
    registry.transition_run("alpha", retry.id, RUN_RUNNING)
    adapter.fail_stage = False
    result = reconciler.reconcile("alpha", "repo", retry.id, ENVELOPE)

    assert result.status == "published"
    assert result.version.startswith("version_")
    assert registry.get("alpha").sources["repo"].active_version == result.version
    assert registry.get("alpha").runs[retry.id].status == RUN_SUCCEEDED
