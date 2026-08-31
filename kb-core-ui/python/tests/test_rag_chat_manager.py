"""Contract tests for ChatManager (T11) -- the HTTP/SSE-facing chat surface
sitting on top of ChatWorkflow (T9) and ChatHistoryStore (T10).

Uses the same lightweight retrieval-protocol fake as test_rag_workflow.py
(no real FalkorDB) plus persistence.FakeChatThreadAdapter (no real FalkorDB)
so this file has zero external dependencies and runs fast.
"""

from __future__ import annotations

import pytest

from kb_core_ui.rag import (
    AdapterError,
    ChatManager,
    ChatManagerError,
    ChatHistoryStore,
    FakeChatBackend,
    FakeChatThreadAdapter,
    RagConfig,
    WorkspaceError,
    WorkspaceRegistry,
)


def _config(**overrides) -> RagConfig:
    values = {
        "RAG_ENABLE": "true",
        "FALKORDB_URL": "falkor://fake:6379",
        "RAG_LLM_PROVIDER": "harness-fake",
        "RAG_LLM_MODEL": "harness-fake",
        "RAG_EMBEDDING_MODEL": "harness-fake",
    }
    values.update(overrides)
    return RagConfig.from_env(values)


class _FakeAdapter:
    """Retrieval-only protocol double, mirrors test_rag_workflow.py's
    _FakeAdapter with a workspace_id so ChatManager's per-call adapter
    lifecycle (adapter_factory/close) works unmodified."""

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.lexical = []
        self.vector = []
        self.expansion_rows = []

    def fulltext_search(self, query, limit, source_ids):
        return [c for c in self.lexical if not source_ids or c.source_id in source_ids][:limit]

    def vector_search(self, embedding, limit, source_ids):
        return [c for c in self.vector if not source_ids or c.source_id in source_ids][:limit]

    def read_query(self, query, params=None):
        if "MATCH (seed:KnowledgeNode" in query:
            return self.expansion_rows
        raise AssertionError(f"unexpected read_query in test fake: {query}")


def _registry(tmp_path) -> WorkspaceRegistry:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    return registry


def _manager(tmp_path, *, backend=None, **kwargs) -> ChatManager:
    registry = _registry(tmp_path)
    config = kwargs.pop("config", None) or _config()
    shared_backend = backend if backend is not None else FakeChatBackend()
    adapters: dict[str, _FakeAdapter] = {}

    def adapter_factory(workspace_id: str) -> _FakeAdapter:
        adapter = _FakeAdapter(workspace_id)
        adapters[workspace_id] = adapter
        return adapter

    def history_store_factory(adapter: _FakeAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=shared_backend), config=config
        )

    manager = ChatManager(
        registry,
        config,
        adapter_factory=adapter_factory,
        history_store_factory=history_store_factory,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    manager._adapters = adapters  # test-only introspection hook
    return manager


def test_default_manager_rejects_unimplemented_provider_instead_of_using_fake(tmp_path):
    config = _config(
        RAG_LLM_PROVIDER="openai",
        RAG_LLM_MODEL="gpt-test",
        RAG_EMBEDDING_MODEL="harness-fake",
    )

    with pytest.raises(ValueError, match="unsupported RAG_LLM_PROVIDER 'openai'"):
        ChatManager(_registry(tmp_path), config)


# --------------------------------------------------------------------------- #
# ask() -- complete (non-streaming) chat
# --------------------------------------------------------------------------- #


def test_ask_returns_contract_payload_shape(tmp_path):
    manager = _manager(tmp_path)
    payload = manager.ask("alpha", query="what does this cover?")

    for key in (
        "answer",
        "query_id",
        "context",
        "explain_graph",
        "source_map",
        "strategy",
        "degraded",
        "error",
        "citations",
        "insufficient_evidence",
        "errors",
        "timings",
    ):
        assert key in payload
    assert payload["error"] == ""
    assert payload["query_id"]
    # The workflow's evidence list travels under the contract name only.
    assert "evidence" not in payload


def test_ask_with_thread_id_persists_turn(tmp_path):
    manager = _manager(tmp_path)
    manager.ask("alpha", query="hello", thread_id="t1")

    thread = manager.list_thread("alpha", "t1")
    assert thread["thread_id"] == "t1"
    # A replayed turn carries the same contract shape as a live answer.
    replayed = thread["turns"][0]["response"]
    assert "context" in replayed and "evidence" not in replayed
    assert set(replayed) >= {"explain_graph", "source_map", "error"}
    assert len(thread["turns"]) == 1
    assert thread["turns"][0]["query"] == "hello"


def test_ask_without_thread_id_does_not_persist(tmp_path):
    manager = _manager(tmp_path)
    manager.ask("alpha", query="hello")

    with pytest.raises(ChatManagerError) as excinfo:
        manager.list_thread("alpha", "t1")
    assert excinfo.value.status == 404


def test_ask_unknown_workspace_raises_workspace_error(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(WorkspaceError):
        manager.ask("does-not-exist", query="hello")


def test_ask_duplicate_in_flight_query_id_returns_409(tmp_path):
    manager = _manager(tmp_path)
    manager._active_query_ids.add("dup")
    with pytest.raises(ChatManagerError) as excinfo:
        manager.ask("alpha", query="hello", query_id="dup")
    assert excinfo.value.status == 409


def test_check_body_size_413(tmp_path):
    manager = _manager(tmp_path, max_body_bytes=10)
    with pytest.raises(ChatManagerError) as excinfo:
        manager.check_body_size(b"0123456789ABCDEF")
    assert excinfo.value.status == 413


# --------------------------------------------------------------------------- #
# open_stream() -- SSE event sequence
# --------------------------------------------------------------------------- #


def test_open_stream_emits_queued_tokens_then_completed_and_persists(tmp_path):
    manager = _manager(tmp_path)
    events = list(manager.open_stream("alpha", query="hello", thread_id="t1")())

    names = [name for name, _ in events]
    assert names[0] == "queued"
    assert names[-1] == "completed"
    assert names.count("completed") == 1
    assert "token" in names

    thread = manager.list_thread("alpha", "t1")
    assert len(thread["turns"]) == 1


def test_open_stream_emits_heartbeats_carrying_no_content(tmp_path):
    manager = _manager(tmp_path)
    events = list(manager.open_stream("alpha", query="hello")())

    names = [name for name, _ in events]
    assert "heartbeat" in names
    assert names.index("heartbeat") < names.index("completed")
    assert all(data == {} for name, data in events if name == "heartbeat")


def test_open_stream_without_thread_id_does_not_persist(tmp_path):
    manager = _manager(tmp_path)
    list(manager.open_stream("alpha", query="hello")())

    with pytest.raises(ChatManagerError):
        manager.list_thread("alpha", "t1")


def test_open_stream_exceeding_concurrency_cap_returns_429(tmp_path):
    manager = _manager(tmp_path, max_concurrent_streams=1)
    manager.open_stream("alpha", query="first")  # reserves capacity, never iterated
    with pytest.raises(ChatManagerError) as excinfo:
        manager.open_stream("alpha", query="second")
    assert excinfo.value.status == 429


def test_open_stream_duplicate_in_flight_query_id_returns_409(tmp_path):
    manager = _manager(tmp_path)
    manager._active_query_ids.add("dup")
    with pytest.raises(ChatManagerError) as excinfo:
        manager.open_stream("alpha", query="hello", query_id="dup")
    assert excinfo.value.status == 409


def test_open_stream_cancelled_before_start_emits_cancelled_only(tmp_path):
    manager = _manager(tmp_path)
    factory = manager.open_stream("alpha", query="hello", thread_id="t1", query_id="q1")
    manager.cancel("alpha", "q1")
    events = list(factory())

    names = [name for name, _ in events]
    assert names == ["queued", "cancelled"]
    with pytest.raises(ChatManagerError):
        manager.list_thread("alpha", "t1")


def test_open_stream_adapter_error_emits_error_event_503(tmp_path):
    registry = _registry(tmp_path)
    config = _config()

    def failing_adapter_factory(workspace_id: str) -> _FakeAdapter:
        raise AdapterError("simulated FalkorDB connection failure")

    manager = ChatManager(
        registry,
        config,
        adapter_factory=failing_adapter_factory,
        sleep=lambda _seconds: None,
    )
    events = list(manager.open_stream("alpha", query="hello")())

    names = [name for name, _ in events if name != "heartbeat"]
    assert names == ["queued", "error"]
    error_data = dict(events[-1][1])
    assert error_data["status"] == 503


def test_open_stream_releases_concurrency_slot_after_completion(tmp_path):
    manager = _manager(tmp_path, max_concurrent_streams=1)
    list(manager.open_stream("alpha", query="hello")())
    # Slot released in the generator's finally -- a second stream must succeed.
    list(manager.open_stream("alpha", query="again")())


# --------------------------------------------------------------------------- #
# cancel()
# --------------------------------------------------------------------------- #


def test_cancel_active_query_marks_cancelled(tmp_path):
    manager = _manager(tmp_path)
    manager._active_query_ids.add("q1")
    result = manager.cancel("alpha", "q1")
    assert result["cancelled"] is True
    assert "q1" in manager._cancelled_query_ids


def test_cancel_completed_query_reports_already_completed(tmp_path):
    manager = _manager(tmp_path)
    payload = manager.ask("alpha", query="hello")
    result = manager.cancel("alpha", payload["query_id"])
    assert result["cancelled"] is False
    assert result["reason"] == "already completed"


def test_cancel_unknown_query_returns_404(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ChatManagerError) as excinfo:
        manager.cancel("alpha", "does-not-exist")
    assert excinfo.value.status == 404


# --------------------------------------------------------------------------- #
# suggestions / feedback / source_map / explain_graph
# --------------------------------------------------------------------------- #


def test_suggestions_include_recent_queries_from_thread(tmp_path):
    manager = _manager(tmp_path)
    manager.ask("alpha", query="first question", thread_id="t1")
    result = manager.suggestions("alpha", thread_id="t1")
    assert result["recent_queries"] == ["first question"]
    assert result["suggestions"]


def test_feedback_requires_known_query_id(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ChatManagerError) as excinfo:
        manager.feedback("alpha", query_id="unknown", rating="up")
    assert excinfo.value.status == 404


def test_feedback_rejects_invalid_rating(tmp_path):
    manager = _manager(tmp_path)
    payload = manager.ask("alpha", query="hello")
    with pytest.raises(ChatManagerError) as excinfo:
        manager.feedback("alpha", query_id=payload["query_id"], rating="sideways")
    assert excinfo.value.status == 400


def test_feedback_records_rating(tmp_path):
    manager = _manager(tmp_path)
    payload = manager.ask("alpha", query="hello")
    entry = manager.feedback("alpha", query_id=payload["query_id"], rating="up", comment="great")
    assert entry["rating"] == "up"
    assert entry["comment"] == "great"


def test_source_map_and_explain_graph_use_cached_query(tmp_path):
    manager = _manager(tmp_path)
    payload = manager.ask("alpha", query="hello")
    qid = payload["query_id"]

    source_map = manager.source_map("alpha", qid)
    assert source_map["source_map"] == payload["source_map"]

    explain = manager.explain_graph("alpha", qid)
    assert explain["explain_graph"] == payload["explain_graph"]


def test_source_map_unknown_query_returns_404(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ChatManagerError) as excinfo:
        manager.source_map("alpha", "does-not-exist")
    assert excinfo.value.status == 404


def test_cached_query_scoped_to_its_own_workspace(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    registry.create("beta", "Beta")
    config = _config()
    shared_backend = FakeChatBackend()

    def adapter_factory(workspace_id: str) -> _FakeAdapter:
        return _FakeAdapter(workspace_id)

    def history_store_factory(adapter: _FakeAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=shared_backend), config=config
        )

    manager = ChatManager(
        registry,
        config,
        adapter_factory=adapter_factory,
        history_store_factory=history_store_factory,
    )
    payload = manager.ask("alpha", query="hello")
    with pytest.raises(ChatManagerError) as excinfo:
        manager.source_map("beta", payload["query_id"])
    assert excinfo.value.status == 404


# --------------------------------------------------------------------------- #
# thread retrieval / cleanup
# --------------------------------------------------------------------------- #


def test_list_thread_unknown_returns_404(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(ChatManagerError) as excinfo:
        manager.list_thread("alpha", "missing")
    assert excinfo.value.status == 404


def test_delete_thread_removes_turns(tmp_path):
    manager = _manager(tmp_path)
    manager.ask("alpha", query="hello", thread_id="t1")
    manager.delete_thread("alpha", "t1")
    with pytest.raises(ChatManagerError):
        manager.list_thread("alpha", "t1")


def test_delete_all_threads_scoped_to_workspace(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    registry.create("beta", "Beta")
    config = _config()
    shared_backend = FakeChatBackend()

    def adapter_factory(workspace_id: str) -> _FakeAdapter:
        return _FakeAdapter(workspace_id)

    def history_store_factory(adapter: _FakeAdapter) -> ChatHistoryStore:
        return ChatHistoryStore(
            FakeChatThreadAdapter(adapter.workspace_id, backend=shared_backend), config=config
        )

    manager = ChatManager(
        registry,
        config,
        adapter_factory=adapter_factory,
        history_store_factory=history_store_factory,
    )
    manager.ask("alpha", query="hello", thread_id="t1")
    manager.ask("beta", query="hello", thread_id="t1")

    result = manager.delete_all_threads("alpha")
    assert result["deleted_threads"] == 1
    with pytest.raises(ChatManagerError):
        manager.list_thread("alpha", "t1")
    # beta's identically-named thread is untouched.
    assert manager.list_thread("beta", "t1")["turns"]
