from __future__ import annotations

import json

import pytest

from kb_core_ui.rag import RagConfig, SourceManifest, StageCounts, WorkspaceManager, WorkspaceRegistry
from kb_core_ui.rag.coordinator import IngestionCoordinator, IngestionCoordinatorError


class _Embeddings:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 0.5]


class _Adapter:
    def __init__(self):
        self.manifest = None
        self.envelope = None
        self.closed = False

    def get_source_manifest(self, source_id):
        return self.manifest

    def recover_source(self, source_id, active_version):
        return None

    def begin_source_stage(self, source_id, version, content_hash, extractor_version):
        return None

    def stage_envelope(self, envelope, version):
        self.envelope = envelope

    def verify_source_stage(self, source_id, version):
        return StageCounts.from_envelope(self.envelope)

    def write_embeddings(self, envelope, version, chunk_rows, node_rows):
        assert chunk_rows or node_rows

    def ensure_retrieval_indexes(self, dimension, index_version):
        assert dimension == 3
        return 4

    def publish_source_stage(self, source_id, version, content_hash, extractor_version):
        self.manifest = SourceManifest(source_id, version, content_hash, extractor_version)

    def rollback_source_stage(self, source_id, version):
        return None

    def close(self):
        self.closed = True


def _manager(tmp_path, adapter):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    config = RagConfig.from_env({})
    coordinator = IngestionCoordinator(
        registry,
        adapter_factory=lambda _workspace_id: adapter,
        embeddings=_Embeddings(),
    )
    return WorkspaceManager(
        registry,
        config,
        adapter_factory=lambda _workspace_id: adapter,
        ingestion_coordinator=coordinator,
    )


def test_local_repo_ingestion_executes_through_publish_and_records_counts(tmp_path):
    graph_dir = tmp_path / "repo" / "kb-core-out"
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "src/api.py:Api",
                        "label": "Api",
                        "source_location": "src/api.py:L1",
                        "doc": "API entrypoint",
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )
    adapter = _Adapter()
    manager = _manager(tmp_path, adapter)
    manager.add_source("alpha", "repo", "local_repo", str(tmp_path / "repo"))

    run = manager.start_ingestion("alpha", "repo")

    assert run["status"] == "succeeded"
    assert run["result"]["counts"]["nodes"] == 1
    assert run["result"]["reconcile_status"] == "published"
    assert adapter.closed is True


def test_document_set_ingestion_indexes_chunks_without_external_llm(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("Workspace facts live in FalkorDB.", encoding="utf-8")
    adapter = _Adapter()
    manager = _manager(tmp_path, adapter)
    manager.add_source("alpha", "docs", "document_set", str(docs))

    run = manager.start_ingestion("alpha", "docs")

    assert run["status"] == "succeeded"
    assert run["result"]["counts"]["chunks"] >= 1


def test_missing_local_source_fails_run_instead_of_leaving_it_queued(tmp_path):
    manager = _manager(tmp_path, _Adapter())
    manager.add_source("alpha", "docs", "document_set", str(tmp_path / "missing"))

    with pytest.raises(IngestionCoordinatorError, match="no supported"):
        manager.start_ingestion("alpha", "docs")

    run = next(iter(manager.registry.get("alpha").runs.values()))
    assert run.status == "failed"
    assert run.finished_at
