"""The chat memory routes.

Two things are load-bearing here: the routes are workspace-scoped on the
server, and they do not exist at all when GraphRAG is off.
"""

from __future__ import annotations

import json
import time

from kb_core_ui.memory import ChatMemoryStore
from kb_core_ui.rag import (
    ChatManager,
    RagConfig,
    SyncChatMemorySink,
    ThreadedChatMemorySink,
    WorkspaceRegistry,
)
from kb_core_ui.rag.persistence import PersistedTurn
from kb_core_ui.server import Server
from kb_core_ui.store import Store

from test_server import request


def _app(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    for workspace_id, name in (("alpha", "Alpha"), ("beta", "Beta")):
        registry.create(workspace_id, name)
    config = RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://fake:6379",
            "RAG_LLM_PROVIDER": "harness-fake",
            "RAG_LLM_MODEL": "harness-fake",
            "RAG_EMBEDDING_MODEL": "harness-fake",
        }
    )
    chat_memory = ChatMemoryStore(str(tmp_path / "memory.db"))
    chat_memory.add("alpha", "t1", "turn-1", 1, "alpha question", "alpha answer about parsers")
    chat_memory.add("alpha", "t2", "turn-2", 1, "second question", "second answer")
    chat_memory.add("beta", "t1", "turn-3", 1, "beta question", "beta answer about parsers")

    store = Store(str(tmp_path / "graph.db"))
    workspace_manager = type("WM", (), {"registry": registry, "config": config})()
    chat_manager = ChatManager(registry, config, chat_memory_sink=SyncChatMemorySink(chat_memory))
    app = Server(
        store,
        str(tmp_path),
        workspace_manager=workspace_manager,
        chat_manager=chat_manager,
        chat_memory=chat_memory,
    )
    return app, store, chat_memory


def _threaded_app(tmp_path):
    """A server whose archive writes go through the real background sink.

    The delay stands in for what an archive write actually costs -- embedding a
    turn can be an HTTP call -- and sits outside the store's lock, exactly where
    the embed call sits, so a delete arriving meanwhile is not merely blocked.
    """

    app, store, memory = _app(tmp_path)
    real_add = memory.add

    def slow_add(*args, **kwargs):
        time.sleep(0.3)
        return real_add(*args, **kwargs)

    memory.add = slow_add
    sink = ThreadedChatMemorySink(SyncChatMemorySink(memory))
    app.chat_memory_sink = sink
    return app, store, memory, sink


def test_listing_returns_only_this_workspaces_entries(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "GET", "/api/rag/workspaces/alpha/memory")

        assert status == 200
        assert body["workspace_id"] == "alpha"
        assert {entry["turn_id"] for entry in body["entries"]} == {"turn-1", "turn-2"}
    finally:
        memory.close()
        store.close()


def test_listing_can_be_narrowed_to_one_thread(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "GET", "/api/rag/workspaces/alpha/memory?thread=t2")

        assert status == 200
        assert [entry["turn_id"] for entry in body["entries"]] == ["turn-2"]
    finally:
        memory.close()
        store.close()


def test_search_never_crosses_a_workspace_boundary(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(
            app, "GET", "/api/rag/workspaces/alpha/memory/search?q=parsers&top=10"
        )

        assert status == 200
        assert body["hits"]
        assert {hit["entry"]["workspace_id"] for hit in body["hits"]} == {"alpha"}
        assert "beta answer" not in json.dumps(body)
    finally:
        memory.close()
        store.close()


def test_deleting_a_thread_leaves_the_rest(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/memory?thread=t1")

        assert status == 200
        assert body["deleted"] == 1
        assert memory.count("alpha") == 1
        assert memory.count("beta") == 1
    finally:
        memory.close()
        store.close()


def test_deleting_without_a_thread_empties_the_workspace_only(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        status, body, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/memory")

        assert status == 200
        assert body["deleted"] == 2
        assert memory.count("alpha") == 0
        assert memory.count("beta") == 1
    finally:
        memory.close()
        store.close()


def test_a_delete_cannot_race_ahead_of_a_queued_write(tmp_path):
    """The threaded sink holds writes that have not landed yet. A delete that
    goes straight to the store steps over that queue, and the write behind it
    then resurrects the rows the caller just asked to remove."""

    app, store, memory, sink = _threaded_app(tmp_path)
    try:
        sink.record(
            PersistedTurn(
                turn_id="turn-late",
                thread_id="t1",
                workspace_id="alpha",
                seq=2,
                query="a late question",
                response={"answer": "a late answer", "citations": []},
                created_at="2026-08-31T00:00:00Z",
            )
        )

        status, _, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/memory")

        assert status == 200
        # The delete waited on its own queue item, which FIFO puts behind the
        # write, so by here both have been applied.
        assert memory.count("alpha") == 0
    finally:
        sink.close()
        memory.close()
        store.close()


def test_an_unknown_workspace_is_refused(tmp_path):
    app, store, memory = _app(tmp_path)
    try:
        assert request(app, "GET", "/api/rag/workspaces/gamma/memory")[0] == 404
        assert request(app, "GET", "/api/rag/workspaces/gamma/memory/search?q=x")[0] == 404
        assert request(app, "DELETE", "/api/rag/workspaces/gamma/memory")[0] == 404
    finally:
        memory.close()
        store.close()


def test_a_server_without_chat_memory_hides_the_routes(tmp_path):
    """No web_dir: the SPA fallback would answer 200 and hide this."""

    store = Store(str(tmp_path / "graph.db"))
    try:
        app = Server(store, str(tmp_path))

        assert request(app, "GET", "/api/rag/workspaces/alpha/memory")[0] == 404
        assert request(app, "GET", "/api/rag/workspaces/alpha/memory/search?q=x")[0] == 404
    finally:
        store.close()
