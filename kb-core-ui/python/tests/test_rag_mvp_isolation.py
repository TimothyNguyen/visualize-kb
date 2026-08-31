"""MVP isolation sweep (T16).

The unit suites prove each boundary in isolation: the adapter parameterizes
scope, the workflow rejects foreign source ids, the history store keys threads
by workspace. This file composes them the way a caller actually reaches
them -- two live workspaces sharing one server, one chat manager, and one
history backend -- so a leak that only appears in the wiring cannot hide.
"""

from __future__ import annotations

import json

from kb_core_ui.rag import (
    ChatHistoryStore,
    ChatManager,
    FakeChatBackend,
    FakeChatThreadAdapter,
    RagConfig,
    SearchCandidate,
    WorkspaceRegistry,
)
from kb_core_ui.server import Server
from kb_core_ui.store import Store

from test_server import request


def _config(enabled: bool = True) -> RagConfig:
    if not enabled:
        return RagConfig.from_env({"RAG_ENABLE": "false"})
    return RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://fake:6379",
            "RAG_LLM_PROVIDER": "harness-fake",
            "RAG_LLM_MODEL": "harness-fake",
            "RAG_EMBEDDING_MODEL": "harness-fake",
        }
    )


class _ScopedAdapter:
    """Answers only with records owned by the workspace it was built for, the
    way a real graph read scoped by ``workspace_id`` does."""

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.source_id = f"{workspace_id}-repo"

    def _candidates(self, source_ids):
        candidate = SearchCandidate(
            f"{self.workspace_id}-node",
            self.source_id,
            f"{self.workspace_id} owns this record about graph records.",
            f"{self.workspace_id}.py:L1",
            4.0,
            "node",
        )
        return [] if source_ids and self.source_id not in source_ids else [candidate]

    def fulltext_search(self, query, limit, source_ids):
        return self._candidates(source_ids)[:limit]

    def vector_search(self, embedding, limit, source_ids):
        return self._candidates(source_ids)[:limit]

    def read_query(self, query, params=None):
        return []


def _app(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    for workspace_id, name in (("alpha", "Alpha"), ("beta", "Beta")):
        registry.create(workspace_id, name)
        registry.add_source(
            workspace_id, f"{workspace_id}-repo", "local_repo", f"fixture://{workspace_id}"
        )
    config = _config()
    # One backend for both workspaces: if the thread key were not workspace
    # scoped, alpha's history would surface under beta here.
    backend = FakeChatBackend()

    def history_store_factory(adapter: _ScopedAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=backend), config=config
        )

    chat_manager = ChatManager(
        registry,
        config,
        adapter_factory=_ScopedAdapter,
        history_store_factory=history_store_factory,
    )
    store = Store(str(tmp_path / "graph.db"))
    workspace_manager = type("WM", (), {"registry": registry, "config": config})()
    app = Server(
        store, str(tmp_path), workspace_manager=workspace_manager, chat_manager=chat_manager
    )
    return app, store


def _ask(app, workspace_id: str, **body):
    body.setdefault("query", "graph records")
    return request(
        app,
        "POST",
        f"/api/rag/workspaces/{workspace_id}/chat",
        json.dumps(body).encode(),
    )


def test_an_answer_carries_only_its_own_workspaces_evidence(tmp_path):
    app, store = _app(tmp_path)
    try:
        status, answer, _ = _ask(app, "beta")
        assert status == 200
        assert {item["source_id"] for item in answer["context"]} == {"beta-repo"}
        assert answer["workspace_id"] == "beta"
        assert "alpha" not in json.dumps(answer)
    finally:
        store.close()


def test_a_foreign_source_id_is_rejected_rather_than_queried(tmp_path):
    app, store = _app(tmp_path)
    try:
        status, answer, _ = _ask(app, "beta", allowed_source_ids=["alpha-repo"])
        assert status == 200
        assert any("rejected_source_ids" in error for error in answer["errors"])
        assert all(item["source_id"] != "alpha-repo" for item in answer["context"])
    finally:
        store.close()


def test_a_query_id_cannot_be_read_from_another_workspace(tmp_path):
    app, store = _app(tmp_path)
    try:
        query_id = _ask(app, "alpha")[1]["query_id"]
        own = request(
            app, "GET", f"/api/rag/workspaces/alpha/chat/source_map?query_id={query_id}"
        )
        assert own[0] == 200
        stolen = request(
            app, "GET", f"/api/rag/workspaces/beta/chat/source_map?query_id={query_id}"
        )
        assert stolen[0] == 404
        explain = request(
            app, "GET", f"/api/rag/workspaces/beta/chat/explain_graph?query_id={query_id}"
        )
        assert explain[0] == 404
    finally:
        store.close()


def test_the_same_thread_id_in_two_workspaces_keeps_two_histories(tmp_path):
    app, store = _app(tmp_path)
    try:
        _ask(app, "alpha", thread_id="shared", query="alpha question")
        _ask(app, "beta", thread_id="shared", query="beta question")

        alpha = request(app, "GET", "/api/rag/workspaces/alpha/chat/threads/shared")[1]
        beta = request(app, "GET", "/api/rag/workspaces/beta/chat/threads/shared")[1]

        assert [turn["query"] for turn in alpha["turns"]] == ["alpha question"]
        assert [turn["query"] for turn in beta["turns"]] == ["beta question"]

        assert request(app, "DELETE", "/api/rag/workspaces/alpha/chat/threads/shared")[0] == 200
        assert request(app, "GET", "/api/rag/workspaces/beta/chat/threads/shared")[1]["turns"]
    finally:
        store.close()


def test_an_unknown_workspace_is_refused_before_any_retrieval(tmp_path):
    app, store = _app(tmp_path)
    try:
        assert _ask(app, "gamma")[0] == 404
        assert request(app, "GET", "/api/rag/workspaces/gamma/chat/threads/shared")[0] == 404
    finally:
        store.close()


def test_disabled_rag_keeps_the_base_ui_and_hides_every_rag_route(tmp_path):
    """V13 as a test, not only as a harness stage: no workspace manager, no
    chat manager, no FalkorDB configuration -- the graph UI still answers."""

    assert _config(enabled=False).enabled is False

    store = Store(str(tmp_path / "graph.db"))
    try:
        # No web_dir: the SPA fallback would answer 200 for a route that does
        # not exist and hide the very thing this asserts.
        app = Server(store, str(tmp_path))
        for path in ("/api/graph", "/api/tree", "/api/stats", "/api/search?q=x"):
            assert request(app, "GET", path)[0] == 200, path
        for path in (
            "/api/rag/workspaces",
            "/api/rag/workspaces/alpha/chat",
            "/api/rag/workspaces/alpha/context",
            "/api/rag/agent",
        ):
            assert request(app, "GET", path)[0] == 404, path
    finally:
        store.close()
