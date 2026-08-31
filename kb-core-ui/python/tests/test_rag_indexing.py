from __future__ import annotations

import pytest

from kb_core_ui.rag import (
    FalkorGraphDocumentLoader,
    FalkorVectorBridge,
    FalkorVectorTypes,
    GraphDocumentTypes,
    HybridRetriever,
    IndexingError,
    RetrievalIndexer,
    RagConfig,
    SearchCandidate,
    normalize_kb_core_graph,
)


ENVELOPE = normalize_kb_core_graph(
    {
        "nodes": [
            {
                "id": "api",
                "label": "API",
                "kind": "SERVICE",
                "doc": "Routes graph searches.",
                "source_location": "api.py:L1",
            },
            {
                "id": "store",
                "label": "Store",
                "kind": "DATABASE",
                "doc": "Persists FalkorDB records.",
                "source_location": "store.py:L1",
            },
        ],
        "links": [{"source": "api", "target": "store", "relation": "USES"}],
    },
    workspace_id="alpha",
    source_id="repo",
).envelope


class Value:
    def __init__(self, **kwargs):
        vars(self).update(kwargs)


class FakeGraph:
    def __init__(self):
        self.calls = []

    def add_graph_documents(self, documents, **kwargs):
        self.calls.append((documents, kwargs))


class DeterministicEmbeddings:
    def __init__(self, dimension: int = 3):
        self.dimension = dimension
        self.documents = []
        self.queries = []

    def embed_documents(self, texts):
        self.documents.extend(texts)
        return [[float(len(text)), 1.0, 0.5][: self.dimension] for text in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return [float(len(text)), 1.0, 0.5][: self.dimension]


class FakeIndexAdapter:
    def __init__(self):
        self.embedding_write = None
        self.index_request = None
        self.lexical = []
        self.vector = []

    def write_embeddings(self, envelope, version, chunk_rows, node_rows):
        self.embedding_write = (envelope, version, chunk_rows, node_rows)

    def ensure_retrieval_indexes(self, dimension, index_version):
        self.index_request = (dimension, index_version)
        return 4

    def fulltext_search(self, query, limit, source_ids):
        self.fulltext_request = (query, limit, source_ids)
        return self.lexical

    def vector_search(self, embedding, limit, source_ids):
        self.vector_request = (embedding, limit, source_ids)
        return self.vector


def test_graph_document_loader_preserves_scope_and_provenance() -> None:
    graph = FakeGraph()
    types = GraphDocumentTypes(Value, Value, Value, Value)

    count = FalkorGraphDocumentLoader(graph, types=types).load(ENVELOPE)

    assert count == 1
    documents, options = graph.calls[0]
    assert options == {"include_source": True}
    graph_document = documents[0]
    assert len(graph_document.nodes) == 2
    assert len(graph_document.relationships) == 1
    assert all(node.properties["workspace_id"] == "alpha" for node in graph_document.nodes)
    assert all(node.properties["source_id"] == "repo" for node in graph_document.nodes)
    assert graph_document.relationships[0].properties["provenance"] == "EXTRACTED"
    assert graph_document.source.metadata["workspace_id"] == "alpha"


def test_retrieval_indexer_embeds_chunks_and_selected_node_text() -> None:
    adapter = FakeIndexAdapter()
    embeddings = DeterministicEmbeddings()

    result = RetrievalIndexer(adapter, embeddings).index_stage(ENVELOPE, "version-next")

    assert result.chunk_embeddings == 2
    assert result.node_embeddings == 2
    assert result.indexes == 4
    assert result.dimension == 3
    _, version, chunk_rows, node_rows = adapter.embedding_write
    assert version == "version-next"
    assert {row["id"] for row in chunk_rows} == {chunk.id for chunk in ENVELOPE.chunks}
    assert all(len(row["embedding"]) == 3 for row in chunk_rows + node_rows)
    assert "API\nRoutes graph searches." in embeddings.documents
    assert adapter.index_request == (3, "kb-core.retrieval.v1")


def test_retrieval_indexer_rejects_inconsistent_embedding_dimensions() -> None:
    class BrokenEmbeddings(DeterministicEmbeddings):
        def embed_documents(self, texts):
            return [[1.0] if index % 2 == 0 else [1.0, 2.0] for index, _ in enumerate(texts)]

    with pytest.raises(IndexingError, match="inconsistent embedding dimensions"):
        RetrievalIndexer(FakeIndexAdapter(), BrokenEmbeddings()).index_stage(
            ENVELOPE, "version-next"
        )


def test_hybrid_retriever_fuses_channels_and_preserves_scope() -> None:
    adapter = FakeIndexAdapter()
    adapter.lexical = [
        SearchCandidate("chunk-a", "repo", "lexical", "a.md", 4.0, "chunk"),
        SearchCandidate("chunk-b", "docs", "both", "b.md", 2.0, "chunk"),
    ]
    adapter.vector = [
        SearchCandidate("chunk-b", "docs", "both", "b.md", 0.1, "chunk"),
        SearchCandidate("node-c", "repo", "vector", "c.py", 0.2, "node"),
    ]
    embeddings = DeterministicEmbeddings()

    hits = HybridRetriever(adapter, embeddings, max_k=10).search(
        "graph store", k=3, source_ids=("repo", "docs")
    )

    assert [hit.id for hit in hits] == ["chunk-b", "chunk-a", "node-c"]
    assert hits[0].channels == ("fulltext", "vector")
    assert adapter.fulltext_request == ("graph store", 6, ("repo", "docs"))
    assert adapter.vector_request[1:] == (6, ("repo", "docs"))
    assert embeddings.queries == ["graph store"]
    with pytest.raises(IndexingError, match="between 1 and 10"):
        HybridRetriever(adapter, embeddings, max_k=10).search("x", k=11)


def test_falkordb_vector_bridge_connects_existing_hybrid_index() -> None:
    class FakeVector:
        calls = []

        @classmethod
        def from_existing_index(cls, **kwargs):
            cls.calls.append(kwargs)
            return "vector-store"

    config = RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://graph.example:6380",
            "FALKORDB_USERNAME": "alice",
            "FALKORDB_PASSWORD": "secret",
            "RAG_LLM_PROVIDER": "fake",
            "RAG_LLM_MODEL": "fake",
            "RAG_EMBEDDING_MODEL": "fake",
        }
    )
    embeddings = DeterministicEmbeddings()

    store = FalkorVectorBridge(
        config,
        "kb_workspace_alpha",
        embeddings,
        types=FalkorVectorTypes(FakeVector, "HYBRID"),
    ).connect("TextChunk", text_property="text")

    assert store == "vector-store"
    call = FakeVector.calls[0]
    assert call["search_type"] == "HYBRID"
    assert call["database"] == "kb_workspace_alpha"
    assert call["host"] == "graph.example"
    assert call["port"] == 6380
    assert call["username"] == "alice"
    assert call["password"] == "secret"
    assert call["embedding_node_property"] == "embedding"
    assert call["text_node_property"] == "text"
