"""LangChain bridge, staged embeddings, and bounded hybrid retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence
from urllib.parse import urlparse

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.contracts import GraphEnvelope

INDEX_VERSION = "kb-core.retrieval.v1"


class IndexingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

    def embed_query(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class GraphDocumentTypes:
    document: type
    node: type
    relationship: type
    graph_document: type

    @classmethod
    def load(cls) -> "GraphDocumentTypes":
        try:
            from langchain_core.documents import Document
            from langchain_falkordb.graphs import GraphDocument, Node, Relationship
        except ImportError:
            raise IndexingError(
                "langchain-falkordb is not installed; install kb-core-ui[rag]"
            ) from None
        return cls(Document, Node, Relationship, GraphDocument)


class FalkorGraphDocumentLoader:
    def __init__(self, graph: Any, *, types: GraphDocumentTypes | None = None):
        self.graph = graph
        self.types = types or GraphDocumentTypes.load()

    def load(self, envelope: GraphEnvelope) -> int:
        nodes = {}
        for item in envelope.nodes:
            nodes[item.id] = self.types.node(
                id=item.id,
                type=item.node_type,
                properties={
                    "workspace_id": item.workspace_id,
                    "source_id": item.source_id,
                    "source_identity": item.source_identity,
                    "label": item.label,
                    "text": item.text,
                    "source_location": item.source_location,
                    "provenance": item.provenance,
                },
            )
        relationships = [
            self.types.relationship(
                source=nodes[item.source],
                target=nodes[item.target],
                type=item.relationship_type,
                properties={
                    "id": item.id,
                    "workspace_id": item.workspace_id,
                    "source_id": item.source_id,
                    "source_location": item.source_location,
                    "provenance": item.provenance,
                },
            )
            for item in envelope.relationships
        ]
        source = self.types.document(
            page_content="\n\n".join(chunk.text for chunk in envelope.chunks),
            metadata={
                "workspace_id": envelope.workspace_id,
                "source_id": envelope.source_id,
                "content_hash": envelope.content_hash,
                "extractor_version": envelope.extractor_version,
            },
        )
        graph_document = self.types.graph_document(
            nodes=list(nodes.values()), relationships=relationships, source=source
        )
        self.graph.add_graph_documents([graph_document], include_source=True)
        return 1


@dataclass(frozen=True)
class FalkorVectorTypes:
    vector: type
    hybrid_search_type: Any

    @classmethod
    def load(cls) -> "FalkorVectorTypes":
        try:
            from langchain_falkordb import FalkorDBVector, SearchType
        except ImportError:
            raise IndexingError(
                "langchain-falkordb is not installed; install kb-core-ui[rag]"
            ) from None
        return cls(FalkorDBVector, SearchType.HYBRID)


class FalkorVectorBridge:
    def __init__(
        self,
        config: RagConfig,
        graph_name: str,
        embeddings: EmbeddingProvider,
        *,
        types: FalkorVectorTypes | None = None,
    ):
        self.config = config
        self.graph_name = graph_name
        self.embeddings = embeddings
        self.types = types or FalkorVectorTypes.load()

    def connect(self, node_label: str, *, text_property: str) -> Any:
        parsed = urlparse(self.config.falkordb_url)
        kwargs: dict[str, Any] = {
            "embedding": self.embeddings,
            "node_label": node_label,
            "search_type": self.types.hybrid_search_type,
            "database": self.graph_name,
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 6379,
            "ssl": self.config.ssl,
            "embedding_node_property": "embedding",
            "text_node_property": text_property,
        }
        if self.config.username:
            kwargs["username"] = self.config.username
        if self.config.password:
            kwargs["password"] = self.config.password
        return self.types.vector.from_existing_index(**kwargs)


@dataclass(frozen=True)
class IndexBuildResult:
    chunk_embeddings: int
    node_embeddings: int
    dimension: int
    indexes: int
    index_version: str


class RetrievalIndexAdapter(Protocol):
    def write_embeddings(
        self,
        envelope: GraphEnvelope,
        version: str,
        chunk_rows: Sequence[dict[str, Any]],
        node_rows: Sequence[dict[str, Any]],
    ) -> None: ...

    def ensure_retrieval_indexes(self, dimension: int, index_version: str) -> int: ...


class RetrievalIndexer:
    def __init__(
        self,
        adapter: RetrievalIndexAdapter,
        embeddings: EmbeddingProvider,
        *,
        index_version: str = INDEX_VERSION,
    ):
        self.adapter = adapter
        self.embeddings = embeddings
        self.index_version = index_version

    def index_stage(self, envelope: GraphEnvelope, version: str) -> IndexBuildResult:
        chunk_texts = [chunk.text for chunk in envelope.chunks]
        node_texts = [
            "\n".join(value for value in (node.label, node.text) if value)
            for node in envelope.nodes
        ]
        texts = chunk_texts + node_texts
        if not texts:
            raise IndexingError("envelope has no indexable text")
        vectors = [list(map(float, value)) for value in self.embeddings.embed_documents(texts)]
        if len(vectors) != len(texts):
            raise IndexingError("embedding provider returned wrong vector count")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise IndexingError("inconsistent embedding dimensions")
        dimension = dimensions.pop()
        if not 1 <= dimension <= 4_096:
            raise IndexingError("embedding dimension must be between 1 and 4096")
        chunk_vectors = vectors[: len(chunk_texts)]
        node_vectors = vectors[len(chunk_texts) :]
        chunk_rows = [
            {"id": chunk.id, "embedding": vector}
            for chunk, vector in zip(envelope.chunks, chunk_vectors)
        ]
        node_rows = [
            {"id": node.id, "embedding": vector, "embedding_text": text}
            for node, text, vector in zip(envelope.nodes, node_texts, node_vectors)
        ]
        self.adapter.write_embeddings(envelope, version, chunk_rows, node_rows)
        indexes = self.adapter.ensure_retrieval_indexes(dimension, self.index_version)
        return IndexBuildResult(
            len(chunk_rows), len(node_rows), dimension, indexes, self.index_version
        )


@dataclass(frozen=True)
class SearchCandidate:
    id: str
    source_id: str
    text: str
    source_location: str
    score: float
    record_type: str


@dataclass(frozen=True)
class RetrievalHit:
    id: str
    source_id: str
    text: str
    source_location: str
    score: float
    record_type: str
    channels: tuple[str, ...]


class HybridSearchAdapter(Protocol):
    def fulltext_search(
        self, query: str, limit: int, source_ids: Sequence[str]
    ) -> Sequence[SearchCandidate]: ...

    def vector_search(
        self, embedding: Sequence[float], limit: int, source_ids: Sequence[str]
    ) -> Sequence[SearchCandidate]: ...


class HybridRetriever:
    def __init__(
        self,
        adapter: HybridSearchAdapter,
        embeddings: EmbeddingProvider,
        *,
        max_k: int = 50,
    ):
        self.adapter = adapter
        self.embeddings = embeddings
        self.max_k = max_k

    def search(
        self, query: str, *, k: int = 5, source_ids: Sequence[str] = ()
    ) -> list[RetrievalHit]:
        if not query.strip():
            raise IndexingError("search query is empty")
        if not 1 <= k <= self.max_k:
            raise IndexingError(f"k must be between 1 and {self.max_k}")
        scoped_sources = tuple(source_ids)
        candidate_limit = min(self.max_k, k * 2)
        lexical = self.adapter.fulltext_search(query, candidate_limit, scoped_sources)
        vector = self.adapter.vector_search(
            list(map(float, self.embeddings.embed_query(query))),
            candidate_limit,
            scoped_sources,
        )
        by_id: dict[str, dict[str, Any]] = {}
        for channel, candidates in (("fulltext", lexical), ("vector", vector)):
            for rank, candidate in enumerate(candidates, start=1):
                value = by_id.setdefault(
                    candidate.id,
                    {"candidate": candidate, "score": 0.0, "channels": []},
                )
                value["score"] += 1.0 / (60 + rank)
                value["channels"].append(channel)
        ordered = sorted(
            by_id.values(),
            key=lambda value: (-value["score"], value["candidate"].id),
        )[:k]
        return [
            RetrievalHit(
                id=value["candidate"].id,
                source_id=value["candidate"].source_id,
                text=value["candidate"].text,
                source_location=value["candidate"].source_location,
                score=value["score"],
                record_type=value["candidate"].record_type,
                channels=tuple(value["channels"]),
            )
            for value in ordered
        ]
