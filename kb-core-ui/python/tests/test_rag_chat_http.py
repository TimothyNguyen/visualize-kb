"""HTTP/SSE contract tests for the chat routes (T11), through Server.serve --
mirrors test_rag_management_surface.py's pattern for the workspace routes.

The transport itself (chunked SSE writes, disconnect handling) is covered by
httpd.py's own tests and the harness's real-subprocess chat_http_contract
stage; this file proves the mux wiring, status-code mapping and SSE framing
are correct at the Response layer.
"""

from __future__ import annotations

import json

from kb_core_ui.rag import (
    AdapterError,
    ChatHistoryStore,
    ChatManager,
    FakeChatBackend,
    FakeChatThreadAdapter,
    RagConfig,
    WorkspaceRegistry,
)
from kb_core_ui.server import Server
from kb_core_ui.store import Store

from test_server import request


def _config() -> RagConfig:
    return RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://fake:6379",
            "RAG_LLM_PROVIDER": "harness-fake",
            "RAG_LLM_MODEL": "harness-fake",
            "RAG_EMBEDDING_MODEL": "harness-fake",
        }
    )


class _FakeAdapter:
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def fulltext_search(self, query, limit, source_ids):
        return []

    def vector_search(self, embedding, limit, source_ids):
        return []

    def read_query(self, query, params=None):
        raise AssertionError(f"unexpected read_query in test fake: {query}")


def _app(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    config = _config()
    backend = FakeChatBackend()

    def adapter_factory(workspace_id: str) -> _FakeAdapter:
        return _FakeAdapter(workspace_id)

    def history_store_factory(adapter: _FakeAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=backend), config=config
        )

    chat_manager = ChatManager(
        registry,
        config,
        adapter_factory=adapter_factory,
        history_store_factory=history_store_factory,
    )
    store = Store(str(tmp_path / "graph.db"))
    wm = type("WM", (), {"registry": registry, "config": config})()
    return Server(store, str(tmp_path), workspace_manager=wm, chat_manager=chat_manager)


def _stream(app, target):
    """Real GET dispatch through the mux, then drains the SSE generator --
    exercises the exact code path Server.serve/_with_cors/write_sse produce,
    not just the domain-level ChatManager.open_stream() used directly by
    test_rag_chat_manager.py."""
    from kb_core_ui.server.wire import Request

    raw_path, _, query_string = target.partition("?")
    import urllib.parse

    req = Request(
        method="GET",
        raw_path=raw_path,
        path=raw_path,
        query=urllib.parse.parse_qs(query_string, keep_blank_values=True),
        query_string=query_string,
        body=b"",
    )
    resp = app.serve(req)
    chunks = list(resp.stream()) if resp.stream is not None else []
    return resp, chunks


def test_chat_disabled_returns_404(tmp_path):
    store = Store(str(tmp_path / "graph.db"))
    app = Server(store, str(tmp_path))
    status, body, _ = request(app, "POST", "/api/rag/workspaces/alpha/chat", b'{"query":"hi"}')
    assert status == 404


def test_post_chat_returns_contract_payload(tmp_path):
    app = _app(tmp_path)
    status, body, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps({"query": "hello", "thread_id": "t1"}).encode(),
    )
    assert status == 200
    for key in ("answer", "query_id", "context", "explain_graph", "source_map", "error"):
        assert key in body

    status, thread, _ = request(app, "GET", "/api/rag/workspaces/alpha/chat/threads/t1")
    assert status == 200
    assert len(thread["turns"]) == 1


def test_post_chat_missing_query_is_400(tmp_path):
    app = _app(tmp_path)
    status, body, _ = request(app, "POST", "/api/rag/workspaces/alpha/chat", b"{}")
    assert status == 400


def test_post_chat_unknown_workspace_is_404(tmp_path):
    app = _app(tmp_path)
    status, body, _ = request(
        app, "POST", "/api/rag/workspaces/nope/chat", json.dumps({"query": "hi"}).encode()
    )
    assert status == 404


def test_post_chat_oversized_body_is_413(tmp_path):
    app = _app(tmp_path)
    big_query = "x" * 70_000
    status, body, _ = request(
        app, "POST", "/api/rag/workspaces/alpha/chat", json.dumps({"query": big_query}).encode()
    )
    assert status == 413


def test_get_chat_stream_emits_sse_frames_ending_in_completed(tmp_path):
    app = _app(tmp_path)
    resp, chunks = _stream(app, "/api/rag/workspaces/alpha/chat/stream?query=hello&thread_id=t1")

    assert resp.status == 200
    assert resp.headers["Content-Type"] == "text/event-stream; charset=utf-8"
    text = b"".join(chunks).decode()
    assert text.startswith("event: queued\n")
    assert "event: completed\n" in text
    assert text.rstrip().endswith("}")

    status, thread, _ = request(app, "GET", "/api/rag/workspaces/alpha/chat/threads/t1")
    assert status == 200 and len(thread["turns"]) == 1


def test_sse_heartbeat_is_a_comment_frame_not_a_dispatchable_event(tmp_path):
    """A heartbeat must be structurally incapable of reaching an EventSource
    listener as content: it is an SSE comment, so it carries no ``event:``
    and no ``data:`` line at all."""

    app = _app(tmp_path)
    _, chunks = _stream(app, "/api/rag/workspaces/alpha/chat/stream?query=hello")
    text = b"".join(chunks).decode()

    assert ": heartbeat\n\n" in text
    assert "event: heartbeat" not in text
    for frame in text.split("\n\n"):
        if frame.startswith(": "):
            assert "data:" not in frame


def test_get_chat_stream_missing_query_is_400(tmp_path):
    app = _app(tmp_path)
    resp, _ = _stream(app, "/api/rag/workspaces/alpha/chat/stream")
    assert resp.status == 400


def test_chat_suggestions_and_feedback_roundtrip(tmp_path):
    app = _app(tmp_path)
    status, ask_body, _ = request(
        app, "POST", "/api/rag/workspaces/alpha/chat", json.dumps({"query": "hello"}).encode()
    )
    assert status == 200
    qid = ask_body["query_id"]

    status, suggestions, _ = request(app, "GET", "/api/rag/workspaces/alpha/chat/suggestions")
    assert status == 200 and suggestions["suggestions"]

    status, feedback, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat/feedback",
        json.dumps({"query_id": qid, "rating": "up"}).encode(),
    )
    assert status == 200 and feedback["rating"] == "up"

    status, source_map, _ = request(
        app, "GET", f"/api/rag/workspaces/alpha/chat/source_map?query_id={qid}"
    )
    assert status == 200 and "source_map" in source_map


def test_chat_cancel_unknown_query_is_404(tmp_path):
    app = _app(tmp_path)
    status, body, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat/cancel",
        json.dumps({"query_id": "missing"}).encode(),
    )
    assert status == 404


def test_delete_thread_then_missing_thread_is_404(tmp_path):
    app = _app(tmp_path)
    request(app, "POST", "/api/rag/workspaces/alpha/chat", json.dumps({"query": "hi", "thread_id": "t1"}).encode())
    status, deleted, _ = request(app, "DELETE", "/api/rag/workspaces/alpha/chat/threads/t1")
    assert status == 200 and deleted["deleted"] is True
    status, _, _ = request(app, "GET", "/api/rag/workspaces/alpha/chat/threads/t1")
    assert status == 404


def test_cors_preflight_on_chat_route(tmp_path):
    app = _app(tmp_path)
    from kb_core_ui.server.wire import Request

    req = Request(
        method="OPTIONS",
        raw_path="/api/rag/workspaces/alpha/chat",
        path="/api/rag/workspaces/alpha/chat",
        query={},
        query_string="",
        body=b"",
    )
    resp = app.serve(req)
    assert resp.status == 204
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
