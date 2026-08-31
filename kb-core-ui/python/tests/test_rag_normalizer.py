from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_core_ui.rag import (
    EXTRACTED,
    INFERRED,
    NormalizationError,
    NormalizationLimits,
    normalize_kb_core_graph,
)

FIXTURES = Path(__file__).parent / "fixtures" / "rag"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def summary(result) -> dict:
    envelope = result.envelope
    return {
        "schema_version": envelope.schema_version,
        "workspace_id": envelope.workspace_id,
        "source_id": envelope.source_id,
        "node_labels": sorted(node.label for node in envelope.nodes),
        "relationship_types": sorted(edge.relationship_type for edge in envelope.relationships),
        "provenance": sorted({node.provenance for node in envelope.nodes}),
        "chunks": len(envelope.chunks),
        "citations": len(envelope.citations),
        "rejected": [item.to_json_dict() for item in result.rejected],
    }


def test_repo_docs_and_cross_repo_golden_contract() -> None:
    repo = normalize_kb_core_graph(
        load_fixture("repo_graph.json"), workspace_id="platform", source_id="api-repo"
    )
    docs = normalize_kb_core_graph(
        load_fixture("docs_graph.json"), workspace_id="platform", source_id="design-docs"
    )
    actual = {"repo": summary(repo), "docs": summary(docs)}

    expected = json.loads((FIXTURES / "normalized_expected.json").read_text(encoding="utf-8"))
    assert actual == expected
    assert {node.id for node in repo.envelope.nodes}.isdisjoint(
        {node.id for node in docs.envelope.nodes}
    )


def test_rejects_duplicate_nodes_dangling_and_duplicate_relationships() -> None:
    graph = load_fixture("repo_graph.json")
    graph["nodes"].append(dict(graph["nodes"][0]))
    graph["links"].append(dict(graph["links"][0]))
    graph["links"].append(
        {"source": "missing", "target": "src/store.py:Store", "relation": "calls"}
    )

    result = normalize_kb_core_graph(graph, workspace_id="platform", source_id="api-repo")

    assert len(result.envelope.nodes) == 2
    assert len(result.envelope.relationships) == 1
    assert [item.reason for item in result.rejected] == [
        "duplicate node id",
        "duplicate relationship",
        "dangling endpoint",
    ]


def test_rejects_oversized_and_non_json_records() -> None:
    graph = {
        "nodes": [
            {"id": "too-long", "label": "12345"},
            {"id": "not-json", "label": "ok", "bad": object()},
            {"id": "valid", "label": "ok", "doc": "bounded"},
        ],
        "links": [],
    }
    result = normalize_kb_core_graph(
        graph,
        workspace_id="platform",
        source_id="api-repo",
        limits=NormalizationLimits(max_label_chars=4),
    )

    assert [node.source_identity for node in result.envelope.nodes] == ["valid"]
    assert [item.reason for item in result.rejected] == [
        "label exceeds 4 characters",
        "record contains non-JSON value",
    ]


def test_rejects_invalid_root_shapes_and_count_limits() -> None:
    with pytest.raises(NormalizationError, match="nodes must be a JSON array"):
        normalize_kb_core_graph(
            {"nodes": {}}, workspace_id="platform", source_id="api-repo"
        )
    with pytest.raises(NormalizationError, match="nodes exceeds limit 1"):
        normalize_kb_core_graph(
            {"nodes": [{"id": "a"}, {"id": "b"}]},
            workspace_id="platform",
            source_id="api-repo",
            limits=NormalizationLimits(max_nodes=1),
        )


def test_provenance_is_explicit_for_repo_and_docs() -> None:
    repo = normalize_kb_core_graph(
        load_fixture("repo_graph.json"), workspace_id="platform", source_id="api-repo"
    )
    docs = normalize_kb_core_graph(
        load_fixture("docs_graph.json"), workspace_id="platform", source_id="design-docs"
    )

    assert {node.provenance for node in repo.envelope.nodes} == {EXTRACTED}
    assert {node.provenance for node in docs.envelope.nodes} == {INFERRED}
