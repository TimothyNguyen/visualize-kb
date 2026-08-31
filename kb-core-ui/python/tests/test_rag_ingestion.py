from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_core_ui.rag import (
    EXTRACTED,
    INFERRED,
    DocumentSetIngestor,
    GraphDocument,
    GraphDocumentNode,
    GraphDocumentRelationship,
    IngestionError,
    RepoGraphIngestor,
    SourceDocument,
    load_document_files,
)


class RecordingExtractor:
    extractor_version = "recording-graphrag.v1"

    def __init__(self):
        self.chunks = []

    def extract(self, chunk) -> GraphDocument:
        self.chunks.append(chunk)
        nodes = []
        relationships = []
        if "Workspace" in chunk.text:
            nodes.append(GraphDocumentNode("workspace", "Workspace", "CONCEPT", "Source scope"))
        if "FalkorDB" in chunk.text:
            nodes.append(GraphDocumentNode("falkordb", "FalkorDB", "DATABASE", "Graph store"))
        if {node.id for node in nodes} == {"workspace", "falkordb"}:
            relationships.append(
                GraphDocumentRelationship("workspace", "falkordb", "USES", "Persists into")
            )
        return GraphDocument(tuple(nodes), tuple(relationships))


def test_repo_ingestor_accepts_object_and_path_with_same_envelope(tmp_path: Path) -> None:
    graph = {
        "nodes": [{"id": "api", "label": "API", "doc": "Entrypoint"}],
        "links": [
            {"source": "api", "target": "missing", "relation": "calls"}
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    ingestor = RepoGraphIngestor()

    from_object = ingestor.ingest(graph, workspace_id="alpha", source_id="repo")
    from_path = ingestor.ingest(path, workspace_id="alpha", source_id="repo")

    assert from_object.envelope.content_hash == from_path.envelope.content_hash
    assert from_object.envelope.metadata["input_format"] == "kb-core-graph-json"
    assert [item.reason for item in from_path.rejected] == ["dangling endpoint"]


def test_document_ingestor_chunks_and_emits_shared_normalized_envelope() -> None:
    extractor = RecordingExtractor()
    ingestor = DocumentSetIngestor(extractor, chunk_size=45, chunk_overlap=8)
    document = SourceDocument(
        title="Architecture",
        text=(
            "Workspace owns repository context. FalkorDB stores graph facts. "
            "Workspace queries remain isolated."
        ),
        source_location="architecture.md",
        source_uri="fixture://architecture.md",
    )

    result = ingestor.ingest([document], workspace_id="alpha", source_id="docs")

    assert len(extractor.chunks) >= 2
    assert all(len(chunk.text) <= 45 for chunk in extractor.chunks)
    assert result.envelope.workspace_id == "alpha"
    assert result.envelope.source_id == "docs"
    assert result.envelope.extractor_version == "document-set+recording-graphrag.v1"
    assert {node.provenance for node in result.envelope.nodes} == {EXTRACTED, INFERRED}
    assert "USES" in {edge.relationship_type for edge in result.envelope.relationships}
    assert "MENTIONS" in {edge.relationship_type for edge in result.envelope.relationships}
    assert all(citation.source_uri == "fixture://architecture.md" for citation in result.envelope.citations)


def test_document_ingestion_is_deterministic_and_deduplicates_entities() -> None:
    document = SourceDocument(
        title="Workspace",
        text="Workspace uses FalkorDB. Workspace uses FalkorDB.",
        source_location="workspace.md",
    )
    ingestor = DocumentSetIngestor(RecordingExtractor(), chunk_size=28, chunk_overlap=10)

    first = ingestor.ingest([document], workspace_id="alpha", source_id="docs")
    second = ingestor.ingest([document], workspace_id="alpha", source_id="docs")

    assert first.envelope.content_hash == second.envelope.content_hash
    identities = [node.source_identity for node in first.envelope.nodes]
    assert identities.count("entity:workspace") == 1
    assert identities.count("entity:falkordb") == 1


def test_document_file_loader_is_sorted_and_rejects_unsupported_files(tmp_path: Path) -> None:
    second = tmp_path / "b.txt"
    first = tmp_path / "a.md"
    first.write_text("# A\nWorkspace", encoding="utf-8")
    second.write_text("FalkorDB", encoding="utf-8")

    documents = load_document_files([second, first])

    assert [document.title for document in documents] == ["a", "b"]
    assert [document.source_location for document in documents] == [str(first), str(second)]
    unsupported = tmp_path / "data.csv"
    unsupported.write_text("value", encoding="utf-8")
    with pytest.raises(IngestionError, match="unsupported document type"):
        load_document_files([unsupported])


def test_ingestors_reject_malformed_or_empty_input(tmp_path: Path) -> None:
    malformed = tmp_path / "graph.json"
    malformed.write_text("{not-json", encoding="utf-8")
    with pytest.raises(IngestionError, match="cannot read KB Core graph"):
        RepoGraphIngestor().ingest(malformed, workspace_id="alpha", source_id="repo")
    with pytest.raises(IngestionError, match="document text is empty"):
        DocumentSetIngestor(RecordingExtractor()).ingest(
            [SourceDocument("Empty", "  ", "empty.md")],
            workspace_id="alpha",
            source_id="docs",
        )
