"""Frozen v1 wire fixtures for the chat REST/SSE contract (T11).

The files under ``kb-core-ui/contracts/rag-chat/v1`` are the shared,
versioned definition of what the server puts on the wire and what the
TypeScript client (``web/src/api/chat.ts``) is written against. This module
regenerates each one from the real ``Server`` and asserts byte equality, so
any added, removed, renamed or retyped field fails here -- on both sides at
once -- instead of silently drifting apart.

Only wall-clock ``timings`` values are normalized (to ``0.0``); their key set
is still frozen. Everything else, including the SSE framing and heartbeat
comments, is compared exactly as written to the socket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_core_ui.rag import (
    AdapterError,
    ChatHistoryStore,
    ChatManager,
    FakeChatBackend,
    FakeChatThreadAdapter,
    RagConfig,
    SearchCandidate,
    WorkspaceRegistry,
)
from kb_core_ui.server import Server
from kb_core_ui.server.wire import Request
from kb_core_ui.store import Store

from test_server import request

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "rag-chat" / "v1"

FIXTURE_QUERY = "graph records"
FIXTURE_QUERY_ID = "q-fixture-1"
FIXTURE_THREAD_ID = "thread-fixture"
FIXTURE_PASSWORD = "fixture-falkordb-password"


def _config() -> RagConfig:
    return RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://fake:6379",
            "FALKORDB_PASSWORD": FIXTURE_PASSWORD,
            "RAG_LLM_PROVIDER": "harness-fake",
            "RAG_LLM_MODEL": "harness-fake",
            "RAG_EMBEDDING_MODEL": "harness-fake",
        }
    )


class _FixtureAdapter:
    """Retrieval-protocol double returning a fixed cross-source evidence set,
    so the frozen payload actually exercises citations, source_map and
    explain_graph instead of an empty answer."""

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id

    def fulltext_search(self, query, limit, source_ids):
        return [
            SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
            SearchCandidate("chunk-docs", "docs", "Docs describe graph records.", "docs.md", 2.0, "chunk"),
        ][:limit]

    def vector_search(self, embedding, limit, source_ids):
        return [
            SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 0.3, "node"),
        ][:limit]

    def read_query(self, query, params=None):
        return [["node-related", "repo", "Related", "Related repo entity.", "related.py:L1"]]


def _app(tmp_path, *, adapter_factory=None, max_concurrent_streams: int = 4) -> Server:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    registry.add_source("alpha", "repo", "local_repo", "file:///repo", "main")
    registry.add_source("alpha", "docs", "document_set", "file:///docs", "")
    config = _config()
    backend = FakeChatBackend()

    def history_store_factory(adapter: Any) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=backend), config=config
        )

    chat_manager = ChatManager(
        registry,
        config,
        adapter_factory=adapter_factory or _FixtureAdapter,
        history_store_factory=history_store_factory,
        max_concurrent_streams=max_concurrent_streams,
        sleep=lambda _seconds: None,
    )
    store = Store(str(tmp_path / "graph.db"))
    workspace_manager = type("WM", (), {"registry": registry, "config": config})()
    return Server(
        store, str(tmp_path), workspace_manager=workspace_manager, chat_manager=chat_manager
    )


def _dispatch_get(app: Server, target: str):
    """Routes a GET without touching ``resp.stream`` -- an undrained stream
    response is what holds a query id and a concurrency slot in flight."""

    raw_path, _, query_string = target.partition("?")
    import urllib.parse

    return app.serve(
        Request(
            method="GET",
            raw_path=raw_path,
            path=raw_path,
            query=urllib.parse.parse_qs(query_string, keep_blank_values=True),
            query_string=query_string,
            body=b"",
        )
    )


def _drain(resp) -> list[bytes]:
    return list(resp.stream()) if resp.stream is not None else []


def _zero_timings(payload: dict[str, Any]) -> dict[str, Any]:
    timings = payload.get("timings")
    if isinstance(timings, dict):
        payload["timings"] = {key: 0.0 for key in timings}
    return payload


def _normalize_sse(chunks: list[bytes]) -> str:
    """Rebuilds the exact wire text with only ``timings`` values zeroed, so a
    heartbeat comment or a reordered frame still fails the comparison."""

    out: list[str] = []
    for frame in b"".join(chunks).decode("utf-8").split("\n\n"):
        if not frame:
            continue
        if frame.startswith(":"):
            out.append(frame)
            continue
        event_line, _, data_line = frame.partition("\n")
        data = _zero_timings(json.loads(data_line[len("data: ") :]))
        out.append(f"{event_line}\ndata: {json.dumps(data, separators=(',', ':'), sort_keys=False)}")
    return "\n\n".join(out) + "\n\n"


def _frozen(name: str) -> str:
    # newline="" disables universal-newline translation, so a fixture checked
    # out with CRLF fails here instead of silently reading back as LF -- the
    # TypeScript side reads these bytes raw and would not be so forgiving.
    with (CONTRACT_DIR / name).open(encoding="utf-8", newline="") as fixture:
        return fixture.read()


def _dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False) + "\n"


# --------------------------------------------------------------------------- #
# Frozen fixtures
# --------------------------------------------------------------------------- #


def test_complete_chat_response_matches_frozen_fixture(tmp_path):
    app = _app(tmp_path)
    status, body, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps(
            {
                "query": FIXTURE_QUERY,
                "query_id": FIXTURE_QUERY_ID,
                "thread_id": FIXTURE_THREAD_ID,
                "allowed_source_ids": ["repo", "docs"],
                "strategy": "auto",
            }
        ).encode(),
    )

    assert status == 200
    assert _dumps(_zero_timings(body)) == _frozen("chat_complete.json")


def test_thread_replay_matches_frozen_fixture(tmp_path):
    app = _app(tmp_path)
    request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps(
            {
                "query": FIXTURE_QUERY,
                "query_id": FIXTURE_QUERY_ID,
                "thread_id": FIXTURE_THREAD_ID,
            }
        ).encode(),
    )

    status, thread, _ = request(
        app, "GET", f"/api/rag/workspaces/alpha/chat/threads/{FIXTURE_THREAD_ID}"
    )
    assert status == 200
    for turn in thread["turns"]:
        turn["turn_id"] = "turn-fixture-1"
        turn["created_at"] = "2026-01-01T00:00:00Z"
        _zero_timings(turn["response"])
    assert _dumps(thread) == _frozen("chat_thread.json")


def test_stream_matches_frozen_fixture(tmp_path):
    app = _app(tmp_path)
    resp = _dispatch_get(
        app,
        f"/api/rag/workspaces/alpha/chat/stream?query={FIXTURE_QUERY.replace(' ', '+')}"
        f"&query_id={FIXTURE_QUERY_ID}&thread_id={FIXTURE_THREAD_ID}",
    )

    assert resp.status == 200
    assert _normalize_sse(_drain(resp)) == _frozen("chat_stream.sse")


def test_cancelled_stream_matches_frozen_fixture(tmp_path):
    app = _app(tmp_path)
    resp = _dispatch_get(
        app,
        f"/api/rag/workspaces/alpha/chat/stream?query={FIXTURE_QUERY.replace(' ', '+')}"
        f"&query_id={FIXTURE_QUERY_ID}",
    )
    request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat/cancel",
        json.dumps({"query_id": FIXTURE_QUERY_ID}).encode(),
    )

    assert _normalize_sse(_drain(resp)) == _frozen("chat_stream_cancelled.sse")


def test_error_stream_matches_frozen_fixture(tmp_path):
    def failing_adapter_factory(workspace_id: str):
        raise AdapterError("falkordb connection refused")

    app = _app(tmp_path, adapter_factory=failing_adapter_factory)
    resp = _dispatch_get(
        app,
        f"/api/rag/workspaces/alpha/chat/stream?query={FIXTURE_QUERY.replace(' ', '+')}"
        f"&query_id={FIXTURE_QUERY_ID}",
    )

    assert _normalize_sse(_drain(resp)) == _frozen("chat_stream_error.sse")


def test_error_status_mappings_match_frozen_fixture(tmp_path):
    app = _app(tmp_path, max_concurrent_streams=1)

    def failing_adapter_factory(workspace_id: str):
        raise AdapterError("falkordb connection refused")

    unavailable = _app(tmp_path / "unavailable", adapter_factory=failing_adapter_factory)

    cases: list[dict[str, Any]] = []

    def record(name: str, method: str, path: str, status: int, body: Any) -> None:
        cases.append({"case": name, "method": method, "path": path, "status": status, "body": body})

    status, body, _ = request(app, "POST", "/api/rag/workspaces/alpha/chat", b"{}")
    record("missing_query", "POST", "/api/rag/workspaces/alpha/chat", status, body)

    status, body, _ = request(
        app, "POST", "/api/rag/workspaces/nope/chat", json.dumps({"query": "hi"}).encode()
    )
    record("unknown_workspace", "POST", "/api/rag/workspaces/nope/chat", status, body)

    status, body, _ = request(app, "GET", "/api/rag/workspaces/alpha/chat/threads/missing")
    record("unknown_thread", "GET", "/api/rag/workspaces/alpha/chat/threads/missing", status, body)

    # Opening a stream reserves both the query id and the workspace's single
    # stream slot until its generator finishes; leaving it undrained is
    # exactly the "still in flight" state a second caller would hit.
    held = _dispatch_get(
        app,
        f"/api/rag/workspaces/alpha/chat/stream?query=held&query_id={FIXTURE_QUERY_ID}",
    )
    assert held.status == 200

    status, body, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps({"query": "hi", "query_id": FIXTURE_QUERY_ID}).encode(),
    )
    record("duplicate_query_id", "POST", "/api/rag/workspaces/alpha/chat", status, body)

    limited = _dispatch_get(app, "/api/rag/workspaces/alpha/chat/stream?query=second")
    record(
        "too_many_streams",
        "GET",
        "/api/rag/workspaces/alpha/chat/stream",
        limited.status,
        json.loads(limited.body.decode()),
    )

    status, body, _ = request(
        app,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps({"query": "x" * 70_000}).encode(),
    )
    record("body_too_large", "POST", "/api/rag/workspaces/alpha/chat", status, body)

    status, body, _ = request(
        unavailable,
        "POST",
        "/api/rag/workspaces/alpha/chat",
        json.dumps({"query": "hi"}).encode(),
    )
    record("backend_unavailable", "POST", "/api/rag/workspaces/alpha/chat", status, body)

    assert _dumps(cases) == _frozen("errors.json")


def test_no_fixture_leaks_server_only_secrets():
    for path in sorted(CONTRACT_DIR.iterdir()):
        text = path.read_text(encoding="utf-8")
        assert FIXTURE_PASSWORD not in text, path.name
        assert "falkor://" not in text, path.name
