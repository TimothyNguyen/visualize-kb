from __future__ import annotations

from kb_core_ui.rag import EXTRACTED, INFERRED, SCHEMA_VERSION, from_kb_core_graph, stable_record_id


def _graph(edge_key: str = "links") -> dict:
    return {
        "nodes": [
            {
                "id": "src/service.py:Service",
                "label": "Service",
                "file_type": "code",
                "source_file": "src/service.py",
                "source_location": "L10",
                "signature": "class Service",
                "doc": "Coordinates requests.",
                "_origin": "ast",
                "community": 2,
            },
            {
                "id": "docs/design.md:Pipeline",
                "label": "Pipeline",
                "kind": "concept",
                "source_location": "docs/design.md#pipeline",
                "description": "Extraction feeds retrieval.",
                "_origin": "llm",
            },
        ],
        edge_key: [
            {
                "source": "src/service.py:Service",
                "target": "docs/design.md:Pipeline",
                "relation": "described by",
                "weight": 0.8,
            }
        ],
    }


def test_contract_accepts_networkx_links_and_legacy_edges() -> None:
    current = from_kb_core_graph(_graph("links"), workspace_id="acme", source_id="repo")
    legacy = from_kb_core_graph(_graph("edges"), workspace_id="acme", source_id="repo")

    assert current.to_json_dict() == legacy.to_json_dict()
    assert current.schema_version == SCHEMA_VERSION
    assert current.relationships[0].relationship_type == "DESCRIBED_BY"
    assert current.relationships[0].properties == {"weight": 0.8}


def test_contract_ids_and_hash_ignore_input_order() -> None:
    first = _graph()
    reversed_graph = {"nodes": list(reversed(first["nodes"])), "links": first["links"]}

    a = from_kb_core_graph(first, workspace_id="acme", source_id="repo")
    b = from_kb_core_graph(reversed_graph, workspace_id="acme", source_id="repo")

    assert [node.id for node in a.nodes] == [node.id for node in b.nodes]
    assert a.content_hash == b.content_hash
    assert stable_record_id("node", "acme", "repo", "same") == stable_record_id(
        "node", "acme", "repo", "same"
    )
    assert stable_record_id("node", "acme", "repo", "same") != stable_record_id(
        "node", "other", "repo", "same"
    )


def test_contract_emits_source_owned_chunks_citations_and_provenance() -> None:
    envelope = from_kb_core_graph(
        _graph(), workspace_id="acme", source_id="repo", source_uri="https://example.test/acme/repo"
    )

    assert {node.provenance for node in envelope.nodes} == {EXTRACTED, INFERRED}
    assert len(envelope.chunks) == 2
    assert len(envelope.citations) == 2
    assert all(chunk.workspace_id == "acme" and chunk.source_id == "repo" for chunk in envelope.chunks)
    assert all(citation.source_uri == "https://example.test/acme/repo" for citation in envelope.citations)
    assert {citation.chunk_id for citation in envelope.citations} == {chunk.id for chunk in envelope.chunks}
