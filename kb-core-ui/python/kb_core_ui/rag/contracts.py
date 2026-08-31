"""Versioned, provider-neutral graph contract used by GraphRAG ingestion.

The existing KB Core graph export is intentionally not changed. This module
normalizes that export at the RAG boundary so FalkorDB and later document
extractors consume one stable envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "kb-core.rag.v1"
KB_CORE_EXTRACTOR_VERSION = "kb-core-json.v1"

EXTRACTED = "EXTRACTED"
INFERRED = "INFERRED"
AMBIGUOUS = "AMBIGUOUS"
PROVENANCE_VALUES = frozenset({EXTRACTED, INFERRED, AMBIGUOUS})

_TYPE_TOKEN = re.compile(r"[^A-Za-z0-9_]+")
_NODE_FIELDS = {
    "id",
    "label",
    "kind",
    "file_type",
    "source_file",
    "source_location",
    "signature",
    "doc",
    "description",
    "provenance",
    "_origin",
}
_EDGE_FIELDS = {"source", "target", "relation", "kind", "source_location", "provenance", "_origin"}


def stable_record_id(
    prefix: str,
    workspace_id: str,
    source_id: str,
    source_identity: str,
    extractor_version: str = KB_CORE_EXTRACTOR_VERSION,
) -> str:
    """Return machine-independent ID for one source-owned record."""

    canonical = json.dumps(
        [workspace_id, source_id, source_identity, extractor_version],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(canonical).hexdigest()[:24]}"


def _type_token(value: object, fallback: str) -> str:
    token = _TYPE_TOKEN.sub("_", str(value or "").strip()).strip("_").upper()
    return token or fallback


def _provenance(record: Mapping[str, Any]) -> str:
    explicit = str(record.get("provenance", "")).upper()
    if explicit in PROVENANCE_VALUES:
        return explicit
    origin = str(record.get("_origin", "")).lower()
    if origin in {"llm", "inferred", "semantic"}:
        return INFERRED
    if origin == "ambiguous":
        return AMBIGUOUS
    return EXTRACTED


def _properties(record: Mapping[str, Any], excluded: set[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in excluded}


def _text(record: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("signature", "doc", "description"):
        value = str(record.get(key, "")).strip()
        if value and value not in values:
            values.append(value)
    return "\n\n".join(values)


@dataclass(frozen=True)
class GraphNode:
    id: str
    workspace_id: str
    source_id: str
    source_identity: str
    node_type: str
    label: str
    text: str = ""
    source_location: str = ""
    provenance: str = EXTRACTED
    properties: Mapping[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "node_type": self.node_type,
            "label": self.label,
            "text": self.text,
            "source_location": self.source_location,
            "provenance": self.provenance,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class GraphRelationship:
    id: str
    workspace_id: str
    source_id: str
    source: str
    target: str
    relationship_type: str
    provenance: str = EXTRACTED
    source_location: str = ""
    properties: Mapping[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "source": self.source,
            "target": self.target,
            "relationship_type": self.relationship_type,
            "provenance": self.provenance,
            "source_location": self.source_location,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class TextChunk:
    id: str
    workspace_id: str
    source_id: str
    text: str
    source_location: str
    node_ids: Sequence[str]
    provenance: str = EXTRACTED

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "text": self.text,
            "source_location": self.source_location,
            "node_ids": list(self.node_ids),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class Citation:
    id: str
    workspace_id: str
    source_id: str
    chunk_id: str
    title: str
    source_location: str
    source_uri: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "source_location": self.source_location,
            "source_uri": self.source_uri,
        }


@dataclass(frozen=True)
class GraphEnvelope:
    workspace_id: str
    source_id: str
    extractor_version: str
    content_hash: str
    nodes: Sequence[GraphNode]
    relationships: Sequence[GraphRelationship]
    chunks: Sequence[TextChunk]
    citations: Sequence[Citation]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "extractor_version": self.extractor_version,
            "workspace_id": self.workspace_id,
            "source_id": self.source_id,
            "content_hash": self.content_hash,
            "nodes": [node.to_json_dict() for node in self.nodes],
            "relationships": [relationship.to_json_dict() for relationship in self.relationships],
            "chunks": [chunk.to_json_dict() for chunk in self.chunks],
            "citations": [citation.to_json_dict() for citation in self.citations],
            "metadata": dict(self.metadata),
        }


def from_kb_core_graph(
    graph: Mapping[str, Any],
    *,
    workspace_id: str,
    source_id: str,
    source_uri: str = "",
    extractor_version: str = KB_CORE_EXTRACTOR_VERSION,
) -> GraphEnvelope:
    """Map current NetworkX or legacy KB Core graph JSON into RAG envelope.

    Structural validation is a separate pipeline stage. Missing endpoints stay
    representable here so that validator can report every rejected edge.
    """

    raw_nodes = graph.get("nodes", [])
    raw_edges = graph.get("links")
    if raw_edges is None:
        raw_edges = graph.get("edges", [])

    id_map: dict[str, str] = {}
    nodes: list[GraphNode] = []
    chunks: list[TextChunk] = []
    citations: list[Citation] = []

    for raw in raw_nodes:
        source_identity = str(raw.get("id", ""))
        node_id = stable_record_id("node", workspace_id, source_id, source_identity, extractor_version)
        id_map[source_identity] = node_id
        source_location = str(raw.get("source_location") or raw.get("source_file") or "")
        text = _text(raw)
        provenance = _provenance(raw)
        label = str(raw.get("label") or source_identity)
        nodes.append(
            GraphNode(
                id=node_id,
                workspace_id=workspace_id,
                source_id=source_id,
                source_identity=source_identity,
                node_type=_type_token(raw.get("kind") or raw.get("file_type"), "ENTITY"),
                label=label,
                text=text,
                source_location=source_location,
                provenance=provenance,
                properties=_properties(raw, _NODE_FIELDS),
            )
        )
        if text:
            chunk_id = stable_record_id(
                "chunk", workspace_id, source_id, f"node:{source_identity}", extractor_version
            )
            chunks.append(
                TextChunk(
                    id=chunk_id,
                    workspace_id=workspace_id,
                    source_id=source_id,
                    text=text,
                    source_location=source_location,
                    node_ids=(node_id,),
                    provenance=provenance,
                )
            )
            citations.append(
                Citation(
                    id=stable_record_id(
                        "citation", workspace_id, source_id, f"chunk:{source_identity}", extractor_version
                    ),
                    workspace_id=workspace_id,
                    source_id=source_id,
                    chunk_id=chunk_id,
                    title=label,
                    source_location=source_location,
                    source_uri=source_uri,
                )
            )

    relationships: list[GraphRelationship] = []
    for index, raw in enumerate(raw_edges):
        raw_source = str(raw.get("source", ""))
        raw_target = str(raw.get("target", ""))
        identity = f"{raw_source}|{raw.get('relation') or raw.get('kind') or 'RELATED_TO'}|{raw_target}|{index}"
        relationships.append(
            GraphRelationship(
                id=stable_record_id("relationship", workspace_id, source_id, identity, extractor_version),
                workspace_id=workspace_id,
                source_id=source_id,
                source=id_map.get(
                    raw_source,
                    stable_record_id("node", workspace_id, source_id, raw_source, extractor_version),
                ),
                target=id_map.get(
                    raw_target,
                    stable_record_id("node", workspace_id, source_id, raw_target, extractor_version),
                ),
                relationship_type=_type_token(raw.get("relation") or raw.get("kind"), "RELATED_TO"),
                provenance=_provenance(raw),
                source_location=str(raw.get("source_location", "")),
                properties=_properties(raw, _EDGE_FIELDS),
            )
        )

    nodes.sort(key=lambda item: item.id)
    relationships.sort(key=lambda item: item.id)
    chunks.sort(key=lambda item: item.id)
    citations.sort(key=lambda item: item.id)
    digest_input = {
        "nodes": [item.to_json_dict() for item in nodes],
        "relationships": [item.to_json_dict() for item in relationships],
        "chunks": [item.to_json_dict() for item in chunks],
        "citations": [item.to_json_dict() for item in citations],
    }
    content_hash = hashlib.sha256(
        json.dumps(digest_input, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GraphEnvelope(
        workspace_id=workspace_id,
        source_id=source_id,
        extractor_version=extractor_version,
        content_hash=content_hash,
        nodes=tuple(nodes),
        relationships=tuple(relationships),
        chunks=tuple(chunks),
        citations=tuple(citations),
        metadata={"source_uri": source_uri, "input_format": "kb-core-graph-json"},
    )
