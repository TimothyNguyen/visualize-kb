"""Dynamic GraphRAG composition workflow for local and CI verification."""

from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

from kb_core_ui.rag import (
    AdapterError,
    ChatHistoryStore,
    ChatManager,
    ChatRequest,
    ChatResponse,
    ChatWorkflow,
    DocumentSetIngestor,
    FakeChatModel,
    FalkorGraphDocumentLoader,
    FalkorVectorBridge,
    FalkorDBAdapter,
    GraphDocument,
    GraphDocumentNode,
    GraphDocumentRelationship,
    HybridRetriever,
    INSUFFICIENT_EVIDENCE_TEXT,
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
    WorkspaceManager,
)
from kb_core_ui.rag.coordinator import IngestionCoordinator
from kb_core_ui.server import Server
from kb_core_ui.server.httpd import listen_and_serve
from kb_core_ui.store import Store

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
    "langgraph_rag",
    "chat_persistence",
    "chat_http_contract",
    "agui_runtime",
    "scoped_read",
    "workspace_management",
    "ingestion_coordinator",
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


@contextlib.contextmanager
def _serving(app: Server, name: str):
    """Runs the real socket server so a stage speaks HTTP, not method calls."""

    stopped = threading.Event()
    listening = threading.Event()
    bound_port: list[int] = []

    def ready(port: int) -> None:
        bound_port.append(port)
        listening.set()

    thread = threading.Thread(
        target=listen_and_serve,
        args=("127.0.0.1", 0, app),
        kwargs={"stop_event": stopped, "ready": ready},
        name=name,
        daemon=True,
    )
    thread.start()
    if not listening.wait(5) or not bound_port:
        stopped.set()
        raise WorkflowFailure(f"{name} did not start")
    try:
        yield f"http://127.0.0.1:{bound_port[0]}"
    finally:
        stopped.set()
        thread.join(timeout=5)
    if thread.is_alive():
        raise WorkflowFailure(f"{name} did not stop")


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


class _BorrowedAdapter:
    """Let manager exercise adapter operations without owning harness connection."""

    def __init__(self, adapter):
        self.adapter = adapter

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def close(self):
        pass


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
        state["driver"] = driver
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

    def langgraph_rag_stage() -> dict[str, Any]:
        assert adapter is not None
        workspace_id = state["workspace"].id
        source_ids = tuple(sorted(state["envelopes"]))
        config = _config(backend)

        class _RejectingCypherAdapter:
            """Delegates every call to a real adapter; rejects read_query calls
            containing ``blocked_substring`` before they reach the backend."""

            def __init__(self, inner, blocked_substring: str):
                self.inner = inner
                self.blocked_substring = blocked_substring
                self.blocked_calls = 0

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def read_query(self, query, params=None):
                if self.blocked_substring in query:
                    self.blocked_calls += 1
                    raise WorkflowFailure("unsafe cypher reached adapter.read_query")
                return self.inner.read_query(query, params)

        class _GraphExpansionFailingAdapter:
            """Delegates every call to a real adapter; simulates a FalkorDB
            failure only for the bounded one-hop expansion query."""

            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def read_query(self, query, params=None):
                if "seed:KnowledgeNode" in query:
                    raise AdapterError("simulated graph query failure")
                return self.inner.read_query(query, params)

        # 1) Cross-source question returns evidence from allowed sources only.
        workflow = ChatWorkflow(
            adapter=adapter,
            registry=registry,
            chat_model=FakeChatModel(),
            embeddings=state["embeddings"],
            config=config,
        )
        cross_source = workflow.ask(
            ChatRequest(
                workspace_id=workspace_id,
                query="graph records",
                allowed_source_ids=source_ids,
                query_id="cross-source",
            )
        )
        if cross_source.insufficient_evidence or not cross_source.evidence:
            raise WorkflowFailure(
                f"cross-source query returned no evidence: {cross_source.to_json_dict()!r}"
            )
        if not all(item["source_id"] in state["envelopes"] for item in cross_source.evidence):
            raise WorkflowFailure("cross-source evidence escaped allowed sources")

        # 2) A foreign source id supplied by the caller cannot escape scope.
        foreign_response = workflow.ask(
            ChatRequest(
                workspace_id=workspace_id,
                query="graph records",
                allowed_source_ids=(*source_ids, "not-a-real-source"),
                query_id="foreign-source",
            )
        )
        if not any("rejected_source_ids" in err for err in foreign_response.errors):
            raise WorkflowFailure("foreign source id was not rejected by scope validation")
        if any(item["source_id"] == "not-a-real-source" for item in foreign_response.evidence):
            raise WorkflowFailure("foreign source id evidence leaked into response")

        # 3) Empty query path returns an explicit insufficient-evidence answer.
        empty_response = workflow.ask(
            ChatRequest(
                workspace_id=workspace_id,
                query="",
                allowed_source_ids=source_ids,
                query_id="empty-query",
            )
        )
        if not empty_response.insufficient_evidence or empty_response.answer != INSUFFICIENT_EVIDENCE_TEXT:
            raise WorkflowFailure(
                f"empty query did not yield insufficient-evidence answer: {empty_response.to_json_dict()!r}"
            )

        # 4) Deliberately rejected/unsafe generated Cypher never reaches the adapter.
        spy = _RejectingCypherAdapter(adapter, "DETACH DELETE")
        unsafe_workflow = ChatWorkflow(
            adapter=spy,
            registry=registry,
            chat_model=FakeChatModel(unsafe_expansion=True),
            embeddings=state["embeddings"],
            config=config,
        )
        unsafe_response = unsafe_workflow.ask(
            ChatRequest(
                workspace_id=workspace_id,
                query="graph records",
                allowed_source_ids=source_ids,
                query_id="unsafe-cypher",
            )
        )
        if spy.blocked_calls:
            raise WorkflowFailure("unsafe cypher reached adapter.read_query")
        if not any("rejected_cypher" in err for err in unsafe_response.errors):
            raise WorkflowFailure("unsafe generated cypher was not rejected by the validator")
        if not unsafe_response.evidence:
            raise WorkflowFailure("unsafe-cypher rejection lost surviving vector evidence")

        # 5) Simulated graph-query failure returns a degraded-marked answer
        #    while vector evidence still exists.
        failing_workflow = ChatWorkflow(
            adapter=_GraphExpansionFailingAdapter(adapter),
            registry=registry,
            chat_model=FakeChatModel(),
            embeddings=state["embeddings"],
            config=config,
        )
        degraded_response = failing_workflow.ask(
            ChatRequest(
                workspace_id=workspace_id,
                query="graph records",
                allowed_source_ids=source_ids,
                query_id="graph-failure",
            )
        )
        if not degraded_response.degraded:
            raise WorkflowFailure("simulated graph failure did not mark the response degraded")
        if not degraded_response.evidence or degraded_response.insufficient_evidence:
            raise WorkflowFailure("degraded response lost surviving vector evidence")

        # 6) Answer citations all map back to returned evidence (no orphans).
        evidence_ids = {item["id"] for item in cross_source.evidence}
        citation_ids = {citation["evidence_id"] for citation in cross_source.citations}
        if not citation_ids:
            raise WorkflowFailure("cross-source answer produced no citations")
        if not citation_ids <= evidence_ids:
            raise WorkflowFailure(
                f"citations escaped evidence set: {sorted(citation_ids - evidence_ids)!r}"
            )

        return {
            "cross_source_evidence": len(cross_source.evidence),
            "cross_source_citations": len(cross_source.citations),
            "foreign_source_rejected": True,
            "empty_query_insufficient": True,
            "unsafe_cypher_rejected": True,
            "graph_failure_degraded": True,
            "citation_grounding_ok": True,
        }

    def chat_persistence_stage() -> dict[str, Any]:
        assert adapter is not None
        workspace_id = state["workspace"].id
        config = _config(backend)
        driver = state.get("driver")

        def make_store(ws_id: str) -> tuple[FalkorDBAdapter, ChatHistoryStore]:
            ws_driver = driver if backend == "fake" else None
            ws_adapter = FalkorDBAdapter(config, ws_id, driver=ws_driver)
            return ws_adapter, ChatHistoryStore(ws_adapter, config=config)

        def make_response(query_id: str, marker: str) -> ChatResponse:
            return ChatResponse(
                workspace_id=workspace_id,
                query_id=query_id,
                answer=f"Answer referencing {marker} [e1]",
                citations=[
                    {
                        "evidence_id": "e1",
                        "source_id": "repo",
                        "source_location": "repo.py:L1",
                        "origin": "retrieval",
                    }
                ],
                evidence=[
                    {
                        "id": "e1",
                        "source_id": "repo",
                        "text": marker,
                        "source_location": "repo.py:L1",
                        "score": 1.0,
                        "origin": "retrieval",
                    }
                ],
                degraded=False,
                insufficient_evidence=False,
                strategy="auto",
                errors=[],
                timings={},
            )

        # 0) Write the first turn of a thread through a freshly constructed
        #    store bound to the primary workspace.
        primary_adapter, primary_store = make_store(workspace_id)
        primary_store.write_turn("conv-1", "first question", make_response("turn-1", "first-turn"))

        # 1) Restart-safe replay: reconstruct the adapter/store from scratch
        #    against the same durable backend and confirm history survives.
        reopened_adapter, reopened_store = make_store(workspace_id)
        replayed = reopened_store.list_turns("conv-1")
        if len(replayed) != 1 or replayed[0].query != "first question":
            raise WorkflowFailure(f"restart-safe replay lost history: {replayed!r}")

        # 2) Resume the thread: append a second turn and confirm ordering.
        reopened_store.write_turn("conv-1", "second question", make_response("turn-2", "second-turn"))
        resumed = reopened_store.list_turns("conv-1")
        if [t.query for t in resumed] != ["first question", "second question"]:
            raise WorkflowFailure(f"resume did not append turns in order: {resumed!r}")
        if [t.seq for t in resumed] != [1, 2]:
            raise WorkflowFailure(f"resumed turn sequence is not monotonic: {resumed!r}")

        # 3) Workspace isolation: a second workspace using the exact same
        #    thread-identity-looking string must never see or affect turn 1.
        other_workspace_id = f"{workspace_id}-iso"
        if other_workspace_id not in registry.workspaces:
            registry.create(other_workspace_id, "Isolation workspace")
        other_adapter, other_store = make_store(other_workspace_id)
        other_store.write_turn(
            "conv-1", "other workspace question", make_response("turn-1", "other-workspace")
        )
        other_turns = other_store.list_turns("conv-1")
        if [t.query for t in other_turns] != ["other workspace question"]:
            raise WorkflowFailure(f"second workspace thread write failed: {other_turns!r}")
        if [t.query for t in primary_store.list_turns("conv-1")] != [
            "first question",
            "second question",
        ]:
            raise WorkflowFailure("cross-workspace leakage: primary thread was affected")

        # 4) Expire/delete a thread and confirm it is gone.
        reopened_store.delete_thread("conv-1")
        if reopened_store.list_turns("conv-1") != []:
            raise WorkflowFailure("deleted thread is still readable")

        # 5) Cleanup of one workspace's threads must not affect another's.
        other_store.write_turn("conv-2", "second thread question", make_response("turn-1", "second-thread"))
        removed = other_store.cleanup_workspace()
        if removed < 1:
            raise WorkflowFailure(f"cleanup reported no removed threads: {removed!r}")
        if other_store.list_turns("conv-1") != [] or other_store.list_turns("conv-2") != []:
            raise WorkflowFailure("cleanup left threads behind in the cleaned workspace")
        primary_store.write_turn("conv-3", "post-cleanup question", make_response("turn-3", "post-cleanup"))
        if [t.query for t in primary_store.list_turns("conv-3")] != ["post-cleanup question"]:
            raise WorkflowFailure("cleanup of another workspace affected this workspace's threads")

        other_adapter.delete_graph()
        other_adapter.close()

        return {
            "restart_replay_turns": len(replayed),
            "resumed_turns": len(resumed),
            "isolation_workspace": other_workspace_id,
            "removed_on_cleanup": removed,
        }

    def chat_http_contract_stage() -> dict[str, Any]:
        assert adapter is not None
        workspace_id = state["workspace"].id
        config = _config(backend)
        manager = WorkspaceManager(
            registry,
            config,
            adapter_factory=lambda _workspace_id: _BorrowedAdapter(adapter),
        )
        chat = ChatManager(
            registry,
            config,
            adapter_factory=lambda _workspace_id: _BorrowedAdapter(adapter),
            history_store_factory=lambda borrowed: ChatHistoryStore(borrowed, config=config),
            embeddings=state["embeddings"],
            sleep=lambda _seconds: None,
        )
        store = Store(str(work_dir / "chat-http.db"))
        app = Server(
            store,
            str(work_dir),
            workspace_manager=manager,
            chat_manager=chat,
        )
        server = _serving(app, "rag-chat-contract-http")
        origin = server.__enter__()
        base = f"{origin}/api/rag/workspaces/{workspace_id}/chat"

        def request_json(
            method: str, url: str, payload: dict[str, Any] | None = None
        ) -> tuple[int, dict[str, Any]]:
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=body,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf-8"))

        try:
            status, answer = request_json(
                "POST",
                base,
                {"query": "graph records", "thread_id": "http-thread", "query_id": "http-complete"},
            )
            required = {
                "answer", "query_id", "workspace_id", "context", "explain_graph",
                "source_map", "strategy", "degraded", "error",
            }
            if status != 200 or not required <= answer.keys():
                raise WorkflowFailure(f"complete chat contract differs: {status} {answer!r}")

            stream_url = base + "/stream?" + urllib.parse.urlencode(
                {"query": "graph records", "thread_id": "http-stream", "query_id": "http-stream"}
            )
            with urllib.request.urlopen(stream_url, timeout=10) as response:
                stream_text = response.read().decode("utf-8")
            if stream_text.count("event: completed\n") != 1:
                raise WorkflowFailure("SSE stream did not emit exactly one completion")
            if ": heartbeat\n\n" not in stream_text or "event: heartbeat" in stream_text:
                raise WorkflowFailure("SSE heartbeat was not a comment frame")

            cancel_url = base + "/stream?" + urllib.parse.urlencode(
                {"query": "graph records", "query_id": "http-cancel"}
            )
            with urllib.request.urlopen(cancel_url, timeout=10) as response:
                first_frame = response.readline().decode("utf-8") + response.readline().decode("utf-8")
                cancel_status, cancelled = request_json(
                    "POST", base + "/cancel", {"query_id": "http-cancel"}
                )
                cancel_tail = response.read().decode("utf-8")
            if cancel_status != 200 or not cancelled.get("cancelled"):
                raise WorkflowFailure(f"HTTP cancellation failed: {cancel_status} {cancelled!r}")
            if "event: queued" not in first_frame or "event: cancelled" not in cancel_tail:
                raise WorkflowFailure("cancelled SSE stream has wrong terminal event")

            status, suggestions = request_json("GET", base + "/suggestions")
            if status != 200 or not suggestions.get("suggestions"):
                raise WorkflowFailure("suggestions endpoint returned no suggestions")
            status, feedback = request_json(
                "POST", base + "/feedback", {"query_id": "http-complete", "rating": "up"}
            )
            if status != 200 or feedback.get("rating") != "up":
                raise WorkflowFailure("feedback endpoint did not accept completed query")
            for suffix, key in (("source_map?query_id=http-complete", "source_map"),
                                ("explain_graph?query_id=http-complete", "explain_graph")):
                status, payload = request_json("GET", base + "/" + suffix)
                if status != 200 or key not in payload:
                    raise WorkflowFailure(f"chat {key} endpoint failed")
            status, replay = request_json("GET", base + "/threads/http-thread")
            if status != 200 or len(replay.get("turns", [])) != 1:
                raise WorkflowFailure("thread replay endpoint lost complete turn")
            status, error = request_json("POST", base, {})
            if status != 400 or "error" not in error:
                raise WorkflowFailure("chat validation error mapping changed")
        finally:
            server.__exit__(None, None, None)
            store.close()
        return {
            "transport": "http",
            "complete_status": 200,
            "stream_terminal_events": 1,
            "cancelled": True,
            "thread_turns": 1,
            "validation_status": 400,
        }

    def agui_runtime_stage() -> dict[str, Any]:
        """The boundary the self-hosted CopilotKit runtime actually calls.

        CopilotKit runs in Node and forwards browser turns to POST
        /api/rag/agent, so this drives that endpoint over real HTTP and asserts
        AG-UI framing, workspace scope carried in the state snapshot, abort, and
        the scope rejections a browser must never be able to talk its way past.
        """

        assert adapter is not None
        workspace_id = state["workspace"].id
        config = _config(backend)
        manager = WorkspaceManager(
            registry,
            config,
            adapter_factory=lambda _workspace_id: _BorrowedAdapter(adapter),
        )
        chat = ChatManager(
            registry,
            config,
            adapter_factory=lambda _workspace_id: _BorrowedAdapter(adapter),
            history_store_factory=lambda borrowed: ChatHistoryStore(borrowed, config=config),
            embeddings=state["embeddings"],
            sleep=lambda _seconds: None,
        )
        store = Store(str(work_dir / "agui.db"))
        app = Server(store, str(work_dir), workspace_manager=manager, chat_manager=chat)

        def run_input(**overrides: Any) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "threadId": "agui-thread",
                "runId": "agui-run",
                "messages": [{"role": "user", "content": "graph records"}],
                "state": {
                    "workspace_id": workspace_id,
                    "strategy": "auto",
                    "allowed_source_ids": sorted(state["envelopes"]),
                },
            }
            payload.update(overrides)
            return payload

        def post(url: str, payload: dict[str, Any]) -> tuple[int, str]:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return response.status, response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8")

        def frames(text: str) -> list[dict[str, Any]]:
            return [
                json.loads(line[len("data: ") :])
                for line in text.split("\n")
                if line.startswith("data: ")
            ]

        try:
            with _serving(app, "rag-agui-http") as origin:
                agent_url = origin + "/api/rag/agent"

                status, text = post(agent_url, run_input())
                events = frames(text)
                types = [event["type"] for event in events]
                if status != 200 or types[0] != "RUN_STARTED" or types[-1] != "RUN_FINISHED":
                    raise WorkflowFailure(f"AG-UI run framing differs: {status} {types!r}")
                if types.count("RUN_FINISHED") + types.count("RUN_ERROR") != 1:
                    raise WorkflowFailure(f"AG-UI run had more than one terminal event: {types!r}")
                if "TEXT_MESSAGE_CONTENT" not in types:
                    raise WorkflowFailure("AG-UI run streamed no assistant text")
                if ": heartbeat\n\n" not in text or '"heartbeat"' in text:
                    raise WorkflowFailure("AG-UI heartbeat was not a comment frame")

                snapshot = next(
                    event["snapshot"] for event in events if event["type"] == "STATE_SNAPSHOT"
                )
                if snapshot.get("workspace_id") != workspace_id:
                    raise WorkflowFailure("AG-UI state snapshot dropped the workspace scope")
                answer = snapshot["last_answer"]
                if not answer.get("citations") or answer.get("error"):
                    raise WorkflowFailure(f"AG-UI answer was not grounded: {answer!r}")
                cited_sources = {citation["source_id"] for citation in answer["citations"]}
                if not cited_sources <= set(state["envelopes"]):
                    raise WorkflowFailure(f"AG-UI answer cited foreign sources: {cited_sources!r}")

                # Abort: the browser's cancel reaches the same in-flight run id.
                abort_input = run_input(runId="agui-abort", threadId="agui-abort")
                request = urllib.request.Request(
                    agent_url,
                    data=json.dumps(abort_input).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    opening = response.readline().decode("utf-8")
                    cancelled = chat.cancel(workspace_id, "agui-abort")
                    aborted = frames(opening + response.read().decode("utf-8"))
                if not cancelled.get("cancelled"):
                    raise WorkflowFailure("AG-UI run id was not cancellable mid-stream")
                abort_types = [event["type"] for event in aborted]
                if abort_types[-1] != "RUN_ERROR" or "RUN_FINISHED" in abort_types:
                    raise WorkflowFailure(f"aborted AG-UI run did not end in RUN_ERROR: {abort_types!r}")

                unscoped, _ = post(agent_url, run_input(state={"strategy": "auto"}))
                foreign, _ = post(agent_url, run_input(state={"workspace_id": "not-a-workspace"}))
                empty, _ = post(agent_url, run_input(messages=[]))
                if (unscoped, foreign, empty) != (400, 404, 400):
                    raise WorkflowFailure(
                        f"AG-UI scope rejections changed: {(unscoped, foreign, empty)!r}"
                    )
        finally:
            store.close()

        return {
            "transport": "http",
            "run_events": len(types),
            "terminal_events": 1,
            "snapshot_workspace_id": workspace_id,
            "cited_sources": sorted(cited_sources),
            "aborted": True,
            "scope_rejections": {"unscoped": 400, "unknown_workspace": 404, "empty_message": 400},
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

    def management_stage() -> dict[str, Any]:
        assert adapter is not None
        manager = WorkspaceManager(
            registry,
            _config(backend),
            adapter_factory=lambda _workspace_id: _BorrowedAdapter(adapter),
        )
        health = manager.health(state["workspace"].id)
        stats = manager.stats(state["workspace"].id)
        context = manager.graph_context(
            state["workspace"].id,
            source_ids=[state["fixture"]["sources"][0]["id"]],
            limit=2,
        )
        run = manager.start_ingestion(
            state["workspace"].id, state["fixture"]["sources"][0]["id"]
        )
        cancelled = manager.cancel_ingestion(state["workspace"].id, run["id"])
        if not health["connected"] or stats["nodes"] < 1 or not context["records"]:
            raise WorkflowFailure("workspace management reads returned incomplete data")
        if cancelled["status"] != "cancelled":
            raise WorkflowFailure("workspace management cancellation did not persist")
        return {
            "connected": health["connected"],
            "nodes": stats["nodes"],
            "relationships": stats["relationships"],
            "context_records": len(context["records"]),
            "cancelled_run": run["id"],
        }

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

    def coordinator_stage() -> dict[str, Any]:
        workspace_id = "rag-coordinator"
        graph_dir = work_dir / "coordinator-repo" / "kb-core-out"
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path = graph_dir / "graph.json"
        graph_path.write_text(
            json.dumps(state["fixture"]["sources"][0]["graph"]), encoding="utf-8"
        )
        registry.create(workspace_id, "Coordinator")
        config = _config(backend)

        def adapter_factory(selected_workspace_id: str):
            driver = state.get("driver") if backend == "fake" else None
            return FalkorDBAdapter(config, selected_workspace_id, driver=driver)

        coordinator = IngestionCoordinator(
            registry,
            adapter_factory=adapter_factory,
            embeddings=_HarnessEmbeddings(),
        )
        manager = WorkspaceManager(
            registry,
            config,
            adapter_factory=adapter_factory,
            ingestion_coordinator=coordinator,
        )
        manager.add_source(workspace_id, "repo", "local_repo", str(graph_dir.parent))
        run = manager.start_ingestion(workspace_id, "repo")
        stats = manager.stats(workspace_id)
        manager.delete_workspace(workspace_id)
        if run["status"] != "succeeded" or stats["nodes"] < 1:
            raise WorkflowFailure(f"coordinator did not publish source: {run!r}")
        return {
            "run_status": run["status"],
            "nodes": stats["nodes"],
            "reconcile_status": run["result"]["reconcile_status"],
            "workspace_cleaned": True,
        }

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
        ("langgraph_rag", langgraph_rag_stage),
        ("chat_persistence", chat_persistence_stage),
        ("chat_http_contract", chat_http_contract_stage),
        ("agui_runtime", agui_runtime_stage),
        ("scoped_read", read_stage),
        ("workspace_management", management_stage),
        ("ingestion_coordinator", coordinator_stage),
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
