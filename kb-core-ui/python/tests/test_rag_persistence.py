from __future__ import annotations

import json

import pytest

from kb_core_ui.rag import (
    ChatHistoryStore,
    ChatResponse,
    FakeChatBackend,
    FakeChatThreadAdapter,
    PersistenceError,
    RagConfig,
    thread_key,
    validate_thread_id,
)


def _response(
    *,
    workspace_id: str = "alpha",
    query_id: str = "q1",
    answer: str = "Based on the retrieved sources: text [e1]",
) -> ChatResponse:
    return ChatResponse(
        workspace_id=workspace_id,
        query_id=query_id,
        answer=answer,
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
                "text": "Repo parses graph records.",
                "source_location": "repo.py:L1",
                "score": 1.0,
                "origin": "retrieval",
            }
        ],
        degraded=False,
        insufficient_evidence=False,
        strategy="auto",
        errors=[],
        timings={"scope_validation": 0.1},
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


# --------------------------------------------------------------------------- #
# Thread identity
# --------------------------------------------------------------------------- #


def test_thread_key_is_workspace_bound_not_a_bare_caller_id():
    assert thread_key("alpha", "conv-1") != thread_key("beta", "conv-1")
    assert thread_key("alpha", "conv-1") == thread_key("alpha", "conv-1")


def test_invalid_thread_id_is_rejected():
    with pytest.raises(PersistenceError):
        validate_thread_id("Conv 1!")
    with pytest.raises(PersistenceError):
        validate_thread_id("")


# --------------------------------------------------------------------------- #
# Write / restart-safe replay / resume
# --------------------------------------------------------------------------- #


def test_write_and_list_round_trip():
    adapter = FakeChatThreadAdapter("alpha")
    store = ChatHistoryStore(adapter)

    turn = store.write_turn("conv-1", "what parses graph records?", _response())

    assert turn.seq == 1
    turns = store.list_turns("conv-1")
    assert len(turns) == 1
    assert turns[0].query == "what parses graph records?"
    assert turns[0].response["answer"] == _response().answer


def test_restart_safe_replay_reopens_store_against_same_backend():
    backend = FakeChatBackend()
    adapter = FakeChatThreadAdapter("alpha", backend=backend)
    store = ChatHistoryStore(adapter)
    store.write_turn("conv-1", "first question", _response(query_id="q1"))

    # Simulate a process restart: construct a brand new adapter/store bound
    # only to the same durable backend, never to in-process state.
    reopened_adapter = FakeChatThreadAdapter("alpha", backend=backend)
    reopened_store = ChatHistoryStore(reopened_adapter)

    turns = reopened_store.list_turns("conv-1")
    assert len(turns) == 1
    assert turns[0].query == "first question"


def test_resume_thread_appends_second_turn_in_order():
    backend = FakeChatBackend()
    store = ChatHistoryStore(FakeChatThreadAdapter("alpha", backend=backend))
    store.write_turn("conv-1", "first question", _response(query_id="q1"))
    store.write_turn("conv-1", "second question", _response(query_id="q2"))

    turns = store.list_turns("conv-1")
    assert [t.query for t in turns] == ["first question", "second question"]
    assert [t.seq for t in turns] == [1, 2]


# --------------------------------------------------------------------------- #
# Workspace isolation (V11)
# --------------------------------------------------------------------------- #


def test_two_workspaces_with_same_thread_id_string_do_not_leak():
    backend = FakeChatBackend()
    alpha_store = ChatHistoryStore(FakeChatThreadAdapter("alpha", backend=backend))
    beta_store = ChatHistoryStore(FakeChatThreadAdapter("beta", backend=backend))

    alpha_store.write_turn("conv-1", "alpha question", _response(workspace_id="alpha"))
    beta_store.write_turn("conv-1", "beta question", _response(workspace_id="beta"))

    alpha_turns = alpha_store.list_turns("conv-1")
    beta_turns = beta_store.list_turns("conv-1")

    assert [t.query for t in alpha_turns] == ["alpha question"]
    assert [t.query for t in beta_turns] == ["beta question"]


# --------------------------------------------------------------------------- #
# Deletion / expiry / cleanup
# --------------------------------------------------------------------------- #


def test_thread_deletion_makes_history_inaccessible():
    store = ChatHistoryStore(FakeChatThreadAdapter("alpha"))
    store.write_turn("conv-1", "question", _response())
    assert store.list_turns("conv-1")

    store.delete_thread("conv-1")

    assert store.list_turns("conv-1") == []


def test_cleanup_of_one_workspace_does_not_affect_another():
    backend = FakeChatBackend()
    alpha_store = ChatHistoryStore(FakeChatThreadAdapter("alpha", backend=backend))
    beta_store = ChatHistoryStore(FakeChatThreadAdapter("beta", backend=backend))
    alpha_store.write_turn("conv-1", "alpha question", _response(workspace_id="alpha"))
    beta_store.write_turn("conv-1", "beta question", _response(workspace_id="beta"))

    removed = alpha_store.cleanup_workspace()

    assert removed == 1
    assert alpha_store.list_turns("conv-1") == []
    assert [t.query for t in beta_store.list_turns("conv-1")] == ["beta question"]


# --------------------------------------------------------------------------- #
# Retention policy
# --------------------------------------------------------------------------- #


def test_retention_policy_trims_oldest_turns_beyond_max_thread_turns():
    config = _config(RAG_MAX_THREAD_TURNS="2")
    store = ChatHistoryStore(FakeChatThreadAdapter("alpha"), config=config)
    for index in range(4):
        store.write_turn("conv-1", f"question {index}", _response(query_id=f"q{index}"))

    turns = store.list_turns("conv-1")
    assert [t.query for t in turns] == ["question 2", "question 3"]


# --------------------------------------------------------------------------- #
# Atomic/complete-turn-only write API and secrets boundary
# --------------------------------------------------------------------------- #


def test_write_turn_rejects_non_chat_response_payload():
    """The write API only accepts a finished ChatResponse -- it structurally
    cannot be called with incremental deltas or an arbitrary dict/kwargs
    that could smuggle a secret field into persisted state."""

    store = ChatHistoryStore(FakeChatThreadAdapter("alpha"))

    with pytest.raises(PersistenceError):
        store.write_turn(
            "conv-1",
            "question",
            {"answer": "partial answer", "password": "leaked-secret"},  # type: ignore[arg-type]
        )

    assert store.list_turns("conv-1") == []


def test_persisted_turn_json_excludes_provider_secrets_and_config_field_names():
    config = _config(
        FALKORDB_USERNAME="svc-reader",
        FALKORDB_PASSWORD="super-secret-password-value",
    )
    store = ChatHistoryStore(FakeChatThreadAdapter("alpha"), config=config)

    turn = store.write_turn("conv-1", "question", _response())
    payload = json.dumps(turn.to_json_dict())

    # No actual secret value ever appears in the persisted representation.
    assert config.password not in payload
    assert config.username not in payload
    # No known credential-shaped RagConfig field name is a key anywhere in
    # the persisted turn, proving the write boundary is structural (the
    # ChatResponse shape has no such fields) and not just an accident of
    # today's fixture data.
    secret_field_names = ("password", "username", "falkordb_password", "falkordb_username")
    for field_name in secret_field_names:
        assert field_name not in payload
