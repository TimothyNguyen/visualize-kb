"""Synchronous internal ingestion execution coordinator.

The HTTP layer may return a completed run immediately for small hackathon
fixtures. Keeping execution synchronous makes lifecycle transitions and
failure reporting deterministic; a future worker can call the same execute
method without changing the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from kb_core_ui.memory import HashingEmbedder
from kb_core_ui.rag.falkordb_adapter import FalkorDBAdapter
from kb_core_ui.rag.indexing import EmbeddingProvider, RetrievalIndexer
from kb_core_ui.rag.ingestion import (
    SUPPORTED_DOCUMENT_SUFFIXES,
    DocumentChunk,
    DocumentSetIngestor,
    GraphDocument,
    RepoGraphIngestor,
    load_document_files,
)
from kb_core_ui.rag.reconciler import SourceReconciler
from kb_core_ui.rag.workspaces import RUN_FAILED, RUN_RUNNING, WorkspaceError, WorkspaceRegistry


class IngestionCoordinatorError(RuntimeError):
    pass


class _ChunkOnlyExtractor:
    """Deterministic MVP extractor: chunks remain searchable without LLM calls."""

    extractor_version = "chunk-only-v1"

    def extract(self, chunk: DocumentChunk) -> GraphDocument:
        return GraphDocument(nodes=(), relationships=())


class _HashingEmbeddings:
    def __init__(self, dimension: int = 512) -> None:
        self._embedder = HashingEmbedder(dimension)
        self.dimension = dimension

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._embedder.embed(text).tolist() for text in texts]

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embedder.embed(text).tolist()


class IngestionCoordinator:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        *,
        adapter_factory: Callable[[str], object],
        embeddings: EmbeddingProvider | None = None,
    ) -> None:
        self.registry = registry
        self.adapter_factory = adapter_factory
        self.embeddings = embeddings or _HashingEmbeddings()

    @classmethod
    def for_config(cls, registry: WorkspaceRegistry, config) -> "IngestionCoordinator":
        return cls(
            registry,
            adapter_factory=lambda workspace_id: FalkorDBAdapter(config, workspace_id),
        )

    def execute(self, workspace_id: str, source_id: str, run_id: str) -> dict[str, object]:
        run = self.registry.transition_run(workspace_id, run_id, RUN_RUNNING)
        source = self.registry.get(workspace_id).sources[source_id]
        adapter = None
        try:
            normalized = self._normalize(workspace_id, source_id, source.kind, source.uri)
            adapter = self.adapter_factory(workspace_id)
            reconciler = SourceReconciler(
                adapter,
                self.registry,
                stage_indexer=RetrievalIndexer(adapter, self.embeddings).index_stage,
            )
            result = reconciler.reconcile(
                workspace_id, source_id, run_id, normalized.envelope
            )
            self.registry.record_run_result(
                workspace_id,
                run_id,
                {
                    "reconcile_status": result.status,
                    "version": result.version,
                    "counts": {
                        "nodes": result.counts.nodes,
                        "relationships": result.counts.relationships,
                        "chunks": result.counts.chunks,
                        "citations": result.counts.citations,
                    },
                    "rejected": [item.to_json_dict() for item in normalized.rejected],
                },
            )
        except Exception as exc:
            current = self.registry.get_run(workspace_id, run_id)
            if current.status == RUN_RUNNING:
                self.registry.transition_run(workspace_id, run_id, RUN_FAILED, str(exc))
            if isinstance(exc, (WorkspaceError, IngestionCoordinatorError)):
                raise
            raise IngestionCoordinatorError(str(exc)) from exc
        finally:
            if adapter is not None:
                close = getattr(adapter, "close", None)
                if close is not None:
                    close()
        return self.registry.get_run(workspace_id, run_id).to_json_dict()

    def _normalize(self, workspace_id: str, source_id: str, kind: str, uri: str):
        path = Path(uri).expanduser().resolve()
        if kind == "local_repo":
            graph_path = self._repo_graph_path(path)
            return RepoGraphIngestor().ingest(
                graph_path,
                workspace_id=workspace_id,
                source_id=source_id,
                source_uri=graph_path.as_uri(),
            )
        if kind == "document_set":
            paths = self._document_paths(path)
            return DocumentSetIngestor(_ChunkOnlyExtractor()).ingest(
                load_document_files(paths),
                workspace_id=workspace_id,
                source_id=source_id,
            )
        raise IngestionCoordinatorError(
            f"source kind {kind!r} is post-hackathon; use local_repo or document_set"
        )

    @staticmethod
    def _repo_graph_path(path: Path) -> Path:
        candidates = [path] if path.is_file() else [
            path / "kb-core-out" / "graph.json",
            path / "graph.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise IngestionCoordinatorError(
            f"local repo source has no graph.json under {path}"
        )

    @staticmethod
    def _document_paths(path: Path) -> list[Path]:
        if path.is_file():
            paths = [path]
        elif path.is_dir():
            paths = sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES
            )
        else:
            paths = []
        if not paths:
            raise IngestionCoordinatorError(
                f"document source has no supported .md, .markdown, or .txt files under {path}"
            )
        return paths
