"""Repository and document-set loaders for normalized GraphRAG envelopes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from kb_core_ui.rag.normalizer import NormalizationResult, normalize_kb_core_graph

DOCUMENT_EXTRACTOR_VERSION = "document-set"
SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})


class IngestionError(ValueError):
    pass


@dataclass(frozen=True)
class SourceDocument:
    title: str
    text: str
    source_location: str
    source_uri: str = ""


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    title: str
    text: str
    source_location: str
    source_uri: str
    index: int


@dataclass(frozen=True)
class GraphDocumentNode:
    id: str
    label: str
    node_type: str = "ENTITY"
    description: str = ""


@dataclass(frozen=True)
class GraphDocumentRelationship:
    source: str
    target: str
    relationship_type: str = "RELATED_TO"
    description: str = ""


@dataclass(frozen=True)
class GraphDocument:
    nodes: Sequence[GraphDocumentNode]
    relationships: Sequence[GraphDocumentRelationship]


class GraphDocumentExtractor(Protocol):
    extractor_version: str

    def extract(self, chunk: DocumentChunk) -> GraphDocument: ...


class RepoGraphIngestor:
    def ingest(
        self,
        graph: Mapping | str | Path,
        *,
        workspace_id: str,
        source_id: str,
        source_uri: str = "",
    ) -> NormalizationResult:
        payload: Mapping
        if isinstance(graph, Mapping):
            payload = graph
        else:
            path = Path(graph)
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IngestionError(f"cannot read KB Core graph {path}: {exc}") from None
            if not isinstance(value, Mapping):
                raise IngestionError("KB Core graph root must be a JSON object")
            payload = value
        return normalize_kb_core_graph(
            payload,
            workspace_id=workspace_id,
            source_id=source_id,
            source_uri=source_uri,
        )


class DocumentSetIngestor:
    def __init__(
        self,
        extractor: GraphDocumentExtractor,
        *,
        chunk_size: int = 2_000,
        chunk_overlap: int = 200,
    ):
        if chunk_size < 1:
            raise IngestionError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise IngestionError("chunk_overlap must be smaller than chunk_size")
        version = str(getattr(extractor, "extractor_version", "")).strip()
        if not version:
            raise IngestionError("extractor_version is required")
        self.extractor = extractor
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.extractor_version = f"{DOCUMENT_EXTRACTOR_VERSION}+{version}"

    def ingest(
        self,
        documents: Sequence[SourceDocument],
        *,
        workspace_id: str,
        source_id: str,
    ) -> NormalizationResult:
        if not documents:
            raise IngestionError("document set is empty")
        ordered = sorted(
            documents,
            key=lambda item: (item.source_location, item.title, item.source_uri),
        )
        raw_nodes: dict[str, dict] = {}
        raw_relationships: dict[tuple[str, str, str, str], dict] = {}
        source_uris = {document.source_uri for document in ordered if document.source_uri}

        for document_index, document in enumerate(ordered):
            if not document.title.strip():
                raise IngestionError("document title is empty")
            if not document.text.strip():
                raise IngestionError("document text is empty")
            for chunk in self._chunks(document, document_index):
                chunk_identity = f"chunk:{document_index}:{chunk.index}"
                raw_nodes[chunk_identity] = {
                    "id": chunk_identity,
                    "label": f"{document.title} chunk {chunk.index + 1}",
                    "kind": "DOCUMENT_CHUNK",
                    "description": chunk.text,
                    "source_location": chunk.source_location,
                    "_origin": "extracted",
                }
                extracted = self.extractor.extract(chunk)
                extracted_ids = {node.id for node in extracted.nodes}
                for node in extracted.nodes:
                    entity_identity = f"entity:{node.id}"
                    raw_nodes.setdefault(
                        entity_identity,
                        {
                            "id": entity_identity,
                            "label": node.label,
                            "kind": node.node_type,
                            "description": node.description,
                            "source_location": chunk.source_location,
                            "_origin": "llm",
                        },
                    )
                    mention = {
                        "source": chunk_identity,
                        "target": entity_identity,
                        "relation": "MENTIONS",
                        "source_location": chunk.source_location,
                        "_origin": "llm",
                    }
                    raw_relationships[self._relationship_key(mention)] = mention
                for relationship in extracted.relationships:
                    if (
                        relationship.source not in extracted_ids
                        or relationship.target not in extracted_ids
                    ):
                        raise IngestionError("extractor relationship has dangling endpoint")
                    raw = {
                        "source": f"entity:{relationship.source}",
                        "target": f"entity:{relationship.target}",
                        "relation": relationship.relationship_type,
                        "description": relationship.description,
                        "source_location": chunk.source_location,
                        "_origin": "llm",
                    }
                    raw_relationships[self._relationship_key(raw)] = raw

        result = normalize_kb_core_graph(
            {
                "nodes": list(raw_nodes.values()),
                "links": list(raw_relationships.values()),
            },
            workspace_id=workspace_id,
            source_id=source_id,
            source_uri=next(iter(source_uris)) if len(source_uris) == 1 else "",
            extractor_version=self.extractor_version,
        )
        metadata = {
            **result.envelope.metadata,
            "input_format": "graphrag-document-set",
            "document_count": len(ordered),
        }
        return replace(result, envelope=replace(result.envelope, metadata=metadata))

    @staticmethod
    def _relationship_key(raw: Mapping[str, str]) -> tuple[str, str, str, str]:
        return (
            str(raw["source"]),
            str(raw["target"]),
            str(raw["relation"]),
            str(raw.get("description", "")),
        )

    def _chunks(self, document: SourceDocument, document_index: int) -> list[DocumentChunk]:
        text = document.text.strip()
        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(text):
            hard_end = min(start + self.chunk_size, len(text))
            end = hard_end
            if hard_end < len(text):
                split = text.rfind(" ", start + 1, hard_end + 1)
                if split > start + self.chunk_overlap:
                    end = split
            value = text[start:end].strip()
            if value:
                index = len(chunks)
                location = f"{document.source_location}#chunk-{index + 1}"
                chunks.append(
                    DocumentChunk(
                        id=f"document:{document_index}:chunk:{index}",
                        title=document.title,
                        text=value,
                        source_location=location,
                        source_uri=document.source_uri,
                        index=index,
                    )
                )
            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
            while start < len(text) and text[start].isspace():
                start += 1
        return chunks


def load_document_files(paths: Sequence[str | Path]) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for path in sorted((Path(value) for value in paths), key=lambda item: str(item)):
        if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise IngestionError(f"unsupported document type {path.suffix or '<none>'}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise IngestionError(f"cannot read document {path}: {exc}") from None
        documents.append(
            SourceDocument(
                title=path.stem,
                text=text,
                source_location=str(path),
                source_uri=path.resolve().as_uri(),
            )
        )
    if not documents:
        raise IngestionError("document set is empty")
    return documents
