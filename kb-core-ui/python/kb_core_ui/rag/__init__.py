"""Workspace-scoped GraphRAG contracts and adapters."""

from kb_core_ui.rag.contracts import (
    AMBIGUOUS,
    EXTRACTED,
    INFERRED,
    SCHEMA_VERSION,
    Citation,
    GraphEnvelope,
    GraphNode,
    GraphRelationship,
    TextChunk,
    from_kb_core_graph,
    stable_record_id,
)

__all__ = [
    "AMBIGUOUS",
    "EXTRACTED",
    "INFERRED",
    "SCHEMA_VERSION",
    "Citation",
    "GraphEnvelope",
    "GraphNode",
    "GraphRelationship",
    "TextChunk",
    "from_kb_core_graph",
    "stable_record_id",
]
