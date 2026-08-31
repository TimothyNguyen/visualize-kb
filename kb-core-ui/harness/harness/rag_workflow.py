"""Dynamic GraphRAG composition workflow for local and CI verification."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable

from kb_core_ui.rag import (
    DocumentSetIngestor,
    FalkorGraphDocumentLoader,
    FalkorVectorBridge,
    FalkorDBAdapter,
    GraphDocument,
    GraphDocumentNode,
    GraphDocumentRelationship,
    HybridRetriever,
    RagConfig,
    ReconcileError,
    RetrievalIndexer,
    RUN_FAILED,
    RUN_RUNNING,
    SOURCE_READY,
    RepoGraphIngestor,
    SourceDocument,
    SourceReconciler,
    WorkspaceRegistry,
)

from harness.rag_fakes import InMemoryDriver

REPORT_SCHEMA_VERSION = "kb-core.rag-harness.v1"
REQUIRED_STAGES = (
    "workspace_lifecycle",
    "source_ingestion",
    "falkordb_reconcile",
    "retrieval_indexing",
    "idempotent_reconcile",
    "refresh_retry_reconcile",
    "hybrid_retrieval",
    "scoped_read",
    "source_delete_isolation",
    "registry_reopen",
    "graph_cleanup",
)


class WorkflowFailure(RuntimeError):
    pass


def _config(backend: str) -> RagConfig:
    values = dict(os.environ)
    values.setdefault("RAG_ENABLE", "true")
    values.setdefault("FALKORDB_URL", "falkor://127.0.0.1:6379")
    values.setdefault("RAG_LLM_PROVIDER", "harness-fake")
    values.setdefault("RAG_LLM_MODEL", "harness-fake")
    values.setdefault("RAG_EMBEDDING_MODEL", "harness-fake")
    if backend == "fake":
        values["FALKORDB_URL"] = "falkor://fake:6379"
    return RagConfig.from_env(values)


def _stage(report: dict[str, Any], name: str, fn: Callable[[], dict[str, Any]]) -> bool:
    start = time.monotonic()
    try:
        details = fn()
    except Exception as exc:
        report["stages"].append(
            {
                "name": name,
                "status": "failed",
                "duration_ms": round((time.monotonic() - start) * 1000, 3),
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        )
        return False
    report["stages"].append(
        {
            "name": name,
            "status": "passed",
            "duration_ms": round((time.monotonic() - start) * 1000, 3),
            "details": details,
        }
    )
    return True


def _read_counts(adapter: FalkorDBAdapter) -> tuple[int, list[str]]:
    rows = adapter.read_query(
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
        "RETURN count(n), collect(DISTINCT n.source_id)"
    )
    if len(rows) != 1 or len(rows[0]) != 2:
        raise WorkflowFailure(f"unexpected count result: {rows!r}")
    return int(rows[0][0]), sorted(str(value) for value in rows[0][1])


def _source_identities(adapter: FalkorDBAdapter, source_id: str) -> list[str]:
    rows = adapter.read_query(
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id, source_id: $source_id}) "
        "WHERE coalesce(n.active, true) = true RETURN collect(n.source_identity)",
        {"source_id": source_id},
    )
    return sorted(str(value) for value in rows[0][0])


class _FailStageOnce:
    def __init__(self, adapter: FalkorDBAdapter):
        self.adapter = adapter
        self.failed = False

    def __getattr__(self, name: str):
        return getattr(self.adapter, name)

    def stage_envelope(self, envelope, version: str) -> None:
        self.adapter.stage_envelope(envelope, version)
        if not self.failed:
            self.failed = True
            raise RuntimeError("injected post-stage failure")


class _FixtureDocumentExtractor:
    extractor_version = "harness-graphrag.v1"

    def extract(self, chunk) -> GraphDocument:
        nodes = []
        if "Workspace" in chunk.text:
            nodes.append(GraphDocumentNode("workspace", "Workspace", "CONCEPT", "Source scope"))
        if "Knowledge Graph" in chunk.text:
            nodes.append(
                GraphDocumentNode("knowledge-graph", "Knowledge Graph", "CONCEPT", "Graph facts")
            )
        relationships = []
        if len(nodes) == 2:
            relationships.append(
                GraphDocumentRelationship("workspace", "knowledge-graph", "OWNS")
            )
        return GraphDocument(tuple(nodes), tuple(relationships))


class _HarnessEmbeddings:
    dimension = 8

    def _embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        for index, byte in enumerate(text.lower().encode("utf-8")):
            values[(byte + index) % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


class _CaptureFalkorGraph:
    def __init__(self):
        self.documents = []

    def add_graph_documents(self, documents, **kwargs):
        if kwargs != {"include_source": True}:
            raise WorkflowFailure(f"unexpected FalkorDBGraph options: {kwargs!r}")
        self.documents.extend(documents)


def execute_rag_workflow(
    *, backend: str, fixture_path: Path, work_dir: Path, report_path: Path
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "backend": backend,
        "status": "running",
        "required_stages": list(REQUIRED_STAGES),
        "stages": [],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    registry = WorkspaceRegistry(str(work_dir / "workspaces.json"))
    state: dict[str, Any] = {}
    adapter: FalkorDBAdapter | None = None
    indexer: RetrievalIndexer | None = None

    def workspace_stage() -> dict[str, Any]:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        workspace = registry.create(fixture["workspace_id"], fixture["workspace_name"])
        runs = {}
        for source in fixture["sources"]:
            registry.add_source(
                workspace.id, source["id"], source["kind"], source["uri"], source.get("ref", "")
            )
            run = registry.queue_run(workspace.id, source["id"])
            registry.transition_run(workspace.id, run.id, RUN_RUNNING)
            runs[source["id"]] = run.id
        state.update({"fixture": fixture, "workspace": workspace, "runs": runs})
        return {"workspace_id": workspace.id, "sources": sorted(runs)}

    def ingestion_stage() -> dict[str, Any]:
        envelopes = {}
        rejected = {}
        formats = {}
        for source in state["fixture"]["sources"]:
            if source["kind"] in {"local_repo", "github_repo"}:
                result = RepoGraphIngestor().ingest(
                    source["graph"],
                    workspace_id=state["workspace"].id,
                    source_id=source["id"],
                    source_uri=source["uri"],
                )
            else:
                documents = [SourceDocument(**document) for document in source["documents"]]
                result = DocumentSetIngestor(
                    _FixtureDocumentExtractor(), chunk_size=256, chunk_overlap=32
                ).ingest(
                    documents,
                    workspace_id=state["workspace"].id,
                    source_id=source["id"],
                )
            envelopes[source["id"]] = result.envelope
            rejected[source["id"]] = [item.reason for item in result.rejected]
            formats[source["id"]] = result.envelope.metadata["input_format"]
        expected_rejections = state["fixture"].get("expected_rejections", {})
        if rejected != expected_rejections:
            raise WorkflowFailure(
                f"rejections differ: expected {expected_rejections!r}, got {rejected!r}"
            )
        state["envelopes"] = envelopes
        return {
            "nodes": sum(len(value.nodes) for value in envelopes.values()),
            "relationships": sum(len(value.relationships) for value in envelopes.values()),
            "rejected": rejected,
            "formats": formats,
        }

    def reconcile_stage() -> dict[str, Any]:
        nonlocal adapter, indexer
        driver = InMemoryDriver() if backend == "fake" else None
        adapter = FalkorDBAdapter(_config(backend), state["workspace"].id, driver=driver)
        state["embeddings"] = _HarnessEmbeddings()
        indexer = RetrievalIndexer(adapter, state["embeddings"])
        reconciler = SourceReconciler(adapter, registry, stage_indexer=indexer.index_stage)
        results = {}
        index_results = {}
        for source_id, envelope in state["envelopes"].items():
            result = reconciler.reconcile(
                state["workspace"].id, source_id, state["runs"][source_id], envelope
            )
            results[source_id] = result.status
            index_results[source_id] = {
                "chunks": len(envelope.chunks),
                "nodes": len(envelope.nodes),
            }
        state["index_results"] = index_results
        health = adapter.health()
        if not health.connected or not health.graph_exists:
            raise WorkflowFailure(f"FalkorDB unhealthy after reconcile: {health!r}")
        return {"graph_name": adapter.graph_name, "results": results}

    def indexing_stage() -> dict[str, Any]:
        assert adapter is not None
        indexes = adapter.ensure_retrieval_indexes(
            state["embeddings"].dimension, "kb-core.retrieval.v1"
        )
        if indexes != 4:
            raise WorkflowFailure(f"expected four retrieval indexes, got {indexes}")
        graph = _CaptureFalkorGraph()
        loader = FalkorGraphDocumentLoader(graph)
        for envelope in state["envelopes"].values():
            loader.load(envelope)
        vector_stores = 0
        if backend == "falkordb":
            bridge = FalkorVectorBridge(
                _config(backend), adapter.graph_name, state["embeddings"]
            )
            bridge.connect("TextChunk", text_property="text")
            bridge.connect("KnowledgeNode", text_property="text")
            vector_stores = 2
        return {
            "indexes": indexes,
            "graph_documents": len(graph.documents),
            "falkordb_vector_stores": vector_stores,
            "sources": state["index_results"],
        }

    def idempotent_stage() -> dict[str, Any]:
        assert adapter is not None
        reconciler = SourceReconciler(adapter, registry)
        results = {}
        for source_id, envelope in state["envelopes"].items():
            run = registry.queue_run(state["workspace"].id, source_id)
            registry.transition_run(state["workspace"].id, run.id, RUN_RUNNING)
            result = reconciler.reconcile(
                state["workspace"].id, source_id, run.id, envelope
            )
            results[source_id] = result.status
        if set(results.values()) != {"unchanged"}:
            raise WorkflowFailure(f"unchanged replay wrote data: {results!r}")
        return {"results": results}

    def refresh_stage() -> dict[str, Any]:
        assert adapter is not None
        source = state["fixture"]["sources"][0]
        source_id = source["id"]
        previous_identities = _source_identities(adapter, source_id)
        refreshed_graph = json.loads(json.dumps(source["graph"]))
        refreshed_graph["nodes"] = refreshed_graph["nodes"][1:] + [
            {
                "id": "src/search.py:Search",
                "label": "Search",
                "file_type": "code",
                "source_location": "src/search.py:L1",
                "doc": "Searches graph records.",
                "_origin": "ast",
            }
        ]
        refreshed_graph["links"] = []
        refreshed = RepoGraphIngestor().ingest(
            refreshed_graph,
            workspace_id=state["workspace"].id,
            source_id=source_id,
            source_uri=source["uri"],
        ).envelope

        failed_run = registry.queue_run(state["workspace"].id, source_id)
        registry.transition_run(state["workspace"].id, failed_run.id, RUN_RUNNING)
        try:
            SourceReconciler(_FailStageOnce(adapter), registry).reconcile(
                state["workspace"].id, source_id, failed_run.id, refreshed
            )
        except ReconcileError:
            pass
        else:
            raise WorkflowFailure("injected reconciliation failure did not fail")
        if _source_identities(adapter, source_id) != previous_identities:
            raise WorkflowFailure("failed stage changed active source records")

        retry = registry.queue_run(state["workspace"].id, source_id)
        registry.transition_run(state["workspace"].id, retry.id, RUN_RUNNING)
        assert indexer is not None
        result = SourceReconciler(
            adapter, registry, stage_indexer=indexer.index_stage
        ).reconcile(
            state["workspace"].id, source_id, retry.id, refreshed
        )
        expected_identities = sorted(node.source_identity for node in refreshed.nodes)
        actual_identities = _source_identities(adapter, source_id)
        if actual_identities != expected_identities:
            raise WorkflowFailure(
                f"refresh did not replace stale records: {actual_identities!r}"
            )
        state["envelopes"][source_id] = refreshed
        return {
            "failed_run": "rolled_back",
            "retry": result.status,
            "active_identities": actual_identities,
        }

    def hybrid_stage() -> dict[str, Any]:
        assert adapter is not None
        hits = HybridRetriever(adapter, state["embeddings"], max_k=10).search(
            "graph records", k=5, source_ids=tuple(sorted(state["envelopes"]))
        )
        if not hits:
            raise WorkflowFailure("hybrid retrieval returned no evidence")
        if not all(hit.source_id in state["envelopes"] for hit in hits):
            raise WorkflowFailure("hybrid retrieval escaped source scope")
        return {
            "hits": len(hits),
            "channels": sorted({channel for hit in hits for channel in hit.channels}),
            "source_ids": sorted({hit.source_id for hit in hits}),
        }

    def read_stage() -> dict[str, Any]:
        assert adapter is not None
        count, source_ids = _read_counts(adapter)
        expected_count = sum(len(value.nodes) for value in state["envelopes"].values())
        expected_sources = sorted(state["envelopes"])
        if (count, source_ids) != (expected_count, expected_sources):
            raise WorkflowFailure(
                f"scoped read differs: expected {(expected_count, expected_sources)!r}, got {(count, source_ids)!r}"
            )
        return {"node_count": count, "source_ids": source_ids}

    def delete_stage() -> dict[str, Any]:
        assert adapter is not None
        deleted_source = state["fixture"]["sources"][0]["id"]
        adapter.delete_source(deleted_source)
        count, source_ids = _read_counts(adapter)
        remaining = {
            source["id"]
            for source in state["fixture"]["sources"]
            if source["id"] != deleted_source
        }
        expected_count = sum(len(state["envelopes"][source_id].nodes) for source_id in remaining)
        if count != expected_count or source_ids != sorted(remaining):
            raise WorkflowFailure(
                f"source delete leaked: expected {(expected_count, sorted(remaining))!r}, got {(count, source_ids)!r}"
            )
        return {"deleted_source": deleted_source, "remaining_nodes": count, "source_ids": source_ids}

    def reopen_stage() -> dict[str, Any]:
        reopened = WorkspaceRegistry(str(work_dir / "workspaces.json")).get(state["workspace"].id)
        statuses = {source_id: source.status for source_id, source in reopened.sources.items()}
        if set(statuses.values()) != {SOURCE_READY}:
            raise WorkflowFailure(f"persisted source statuses not ready: {statuses!r}")
        return {"source_statuses": statuses}

    def cleanup_stage() -> dict[str, Any]:
        assert adapter is not None
        adapter.delete_graph()
        health = adapter.health()
        if health.graph_exists:
            raise WorkflowFailure("graph still exists after cleanup")
        adapter.close()
        return {"graph_deleted": True}

    stages = (
        ("workspace_lifecycle", workspace_stage),
        ("source_ingestion", ingestion_stage),
        ("falkordb_reconcile", reconcile_stage),
        ("retrieval_indexing", indexing_stage),
        ("idempotent_reconcile", idempotent_stage),
        ("refresh_retry_reconcile", refresh_stage),
        ("hybrid_retrieval", hybrid_stage),
        ("scoped_read", read_stage),
        ("source_delete_isolation", delete_stage),
        ("registry_reopen", reopen_stage),
        ("graph_cleanup", cleanup_stage),
    )
    passed = True
    for name, fn in stages:
        if not passed:
            report["stages"].append({"name": name, "status": "skipped", "duration_ms": 0})
            continue
        passed = _stage(report, name, fn)

    if not passed and state.get("runs"):
        for run_id in state["runs"].values():
            try:
                registry.transition_run(state["workspace"].id, run_id, RUN_FAILED, "harness failed")
            except Exception:
                pass
    report["status"] = "passed" if all(
        stage["status"] == "passed" for stage in report["stages"]
    ) else "failed"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def run_rag_workflow(args) -> int:
    fixture_path = Path(args.fixture).resolve()
    report_path = Path(args.report).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="kb-core-rag-harness-"))
    try:
        report = execute_rag_workflow(
            backend=args.backend,
            fixture_path=fixture_path,
            work_dir=temp_root,
            report_path=report_path,
        )
    finally:
        if not args.keep_work_dir:
            shutil.rmtree(temp_root, ignore_errors=True)
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["status"] == "passed" else 1
    RetrievalIndexer,
