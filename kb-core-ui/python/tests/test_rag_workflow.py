from __future__ import annotations

import pytest

from kb_core_ui.rag import (
    AdapterError,
    ChatRequest,
    ChatWorkflow,
    FakeChatModel,
    INSUFFICIENT_EVIDENCE_TEXT,
    RagConfig,
    RetrievalLimits,
    SearchCandidate,
    UnsafeCypherError,
    WorkspaceRegistry,
    validate_generated_cypher,
)


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


class _Embeddings:
    dimension = 3

    def embed_documents(self, texts):
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0, 0.5]


class _FakeAdapter:
    """Implements the HybridSearchAdapter + GraphReadAdapter surface without a
    second database client -- exercises the exact protocol ChatWorkflow uses.
    """

    def __init__(self):
        self.lexical: list[SearchCandidate] = []
        self.vector: list[SearchCandidate] = []
        self.read_queries: list[tuple[str, dict]] = []
        self.expansion_rows: list[list[object]] = []
        self.fail_expansion_query = False
        self.fail_error = "simulated transient FalkorDB failure"

    def fulltext_search(self, query, limit, source_ids):
        return [c for c in self.lexical if not source_ids or c.source_id in source_ids][:limit]

    def vector_search(self, embedding, limit, source_ids):
        return [c for c in self.vector if not source_ids or c.source_id in source_ids][:limit]

    def read_query(self, query, params=None):
        values = dict(params or {})
        self.read_queries.append((query, values))
        if "MATCH (seed:KnowledgeNode" in query:
            if self.fail_expansion_query:
                raise AdapterError(self.fail_error)
            return self.expansion_rows
        raise AssertionError(f"unexpected read_query in test fake: {query}")


def _registry(tmp_path, sources=("repo", "docs")) -> WorkspaceRegistry:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    for source_id in sources:
        registry.add_source("alpha", source_id, "local_repo", f"fixture://{source_id}")
    return registry


def _workflow(registry, adapter, *, chat_model=None, config=None) -> ChatWorkflow:
    return ChatWorkflow(
        adapter=adapter,
        registry=registry,
        chat_model=chat_model or FakeChatModel(),
        embeddings=_Embeddings(),
        config=config or _config(),
    )


def test_cross_source_question_returns_evidence_from_allowed_sources_only(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
        SearchCandidate("chunk-docs", "docs", "Docs describe graph records.", "docs.md", 2.0, "chunk"),
    ]
    adapter.vector = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 0.3, "node"),
    ]
    adapter.expansion_rows = [
        ["node-related", "repo", "Related", "Related repo entity.", "related.py:L1"],
    ]

    response = _workflow(registry, adapter).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    assert response.insufficient_evidence is False
    assert response.degraded is False
    evidence_source_ids = {item["source_id"] for item in response.evidence}
    assert evidence_source_ids <= {"repo", "docs"}
    assert evidence_source_ids  # non-empty: cross-source evidence was returned
    assert all(c["evidence_id"] in {item["id"] for item in response.evidence} for c in response.citations)


def test_foreign_source_id_cannot_escape_scope(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]

    response = _workflow(registry, adapter).ask(
        ChatRequest(
            workspace_id="alpha",
            query="graph records",
            allowed_source_ids=("repo", "other-workspace-source"),
        )
    )

    assert any("rejected_source_ids" in error for error in response.errors)
    assert all(item["source_id"] != "other-workspace-source" for item in response.evidence)


def test_empty_query_returns_explicit_insufficient_evidence(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]

    response = _workflow(registry, adapter).ask(ChatRequest(workspace_id="alpha", query="   "))

    assert response.insufficient_evidence is True
    assert response.answer == INSUFFICIENT_EVIDENCE_TEXT
    assert response.citations == []
    assert response.evidence == []


def test_unsafe_generated_cypher_never_reaches_adapter(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]
    unsafe_chat_model = FakeChatModel(unsafe_expansion=True)

    response = _workflow(registry, adapter, chat_model=unsafe_chat_model).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    assert adapter.read_queries == []
    assert response.degraded is True
    assert any("rejected_cypher" in error for error in response.errors)
    # retrieval evidence is still usable even though graph expansion was rejected
    assert response.evidence


def test_graph_query_failure_returns_degraded_answer_with_vector_evidence(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]
    adapter.vector = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 0.4, "node"),
    ]
    adapter.fail_expansion_query = True

    response = _workflow(registry, adapter).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    assert response.degraded is True
    assert any("graph_query_failed" in error for error in response.errors)
    assert response.evidence  # vector/lexical evidence survives the graph failure
    assert response.insufficient_evidence is False


def test_answer_citations_all_map_to_returned_evidence(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
        SearchCandidate("chunk-docs", "docs", "Docs describe graph records.", "docs.md", 2.0, "chunk"),
    ]

    response = _workflow(registry, adapter).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    evidence_ids = {item["id"] for item in response.evidence}
    assert response.citations
    assert all(citation["evidence_id"] in evidence_ids for citation in response.citations)


class _AlwaysUngroundedChatModel(FakeChatModel):
    def synthesize(self, query, evidence):
        return super().synthesize(query, evidence).__class__(
            text="Some claim [not-a-real-id]", citation_ids=("not-a-real-id",)
        )


def test_ungrounded_citation_forces_insufficient_evidence_response(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]

    response = _workflow(
        registry, adapter, chat_model=_AlwaysUngroundedChatModel()
    ).ask(ChatRequest(workspace_id="alpha", query="graph records"))

    assert response.insufficient_evidence is True
    assert response.answer == INSUFFICIENT_EVIDENCE_TEXT
    assert response.citations == []


def test_provider_retry_recovers_after_transient_failure(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]
    flaky_model = FakeChatModel(fail_times=1)

    response = _workflow(registry, adapter, chat_model=flaky_model).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    assert any("provider_retry_1" in error for error in response.errors)
    assert response.answer != INSUFFICIENT_EVIDENCE_TEXT
    assert response.evidence


def test_provider_exhausts_retries_returns_explicit_unavailable_answer(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]
    config = _config()
    always_flaky_model = FakeChatModel(fail_times=config.max_provider_retries + 5)

    response = _workflow(registry, adapter, chat_model=always_flaky_model, config=config).ask(
        ChatRequest(workspace_id="alpha", query="graph records")
    )

    assert any("provider_exhausted" in error for error in response.errors)
    assert response.citations == []


def test_cancelled_request_short_circuits_without_calling_provider(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()
    adapter.lexical = [
        SearchCandidate("node-repo", "repo", "Repo parses graph records.", "repo.py:L1", 4.0, "node"),
    ]

    class _ExplodingChatModel(FakeChatModel):
        def synthesize(self, query, evidence):
            raise AssertionError("provider must not be called for a cancelled request")

    response = _workflow(registry, adapter, chat_model=_ExplodingChatModel()).ask(
        ChatRequest(workspace_id="alpha", query="graph records", cancelled=True)
    )

    assert "cancelled" in response.errors
    assert response.answer == "Query was cancelled before completion."


def test_missing_workspace_is_rejected_defensively(tmp_path):
    registry = _registry(tmp_path)
    adapter = _FakeAdapter()

    response = _workflow(registry, adapter).ask(
        ChatRequest(workspace_id="does-not-exist", query="graph records")
    )

    assert response.insufficient_evidence is True
    assert any("invalid_workspace" in error for error in response.errors)


def test_retrieval_limits_resolve_bounds_request_to_config_max():
    config = _config()

    limits = RetrievalLimits.resolve(config, requested_k=999, requested_graph_row_limit=999)
    assert limits.hybrid_k == config.max_hybrid_k
    assert limits.graph_row_limit == config.max_graph_row_limit

    narrower = RetrievalLimits.resolve(config, requested_k=1, requested_graph_row_limit=1)
    assert narrower.hybrid_k == 1
    assert narrower.graph_row_limit == 1


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) RETURN n.id LIMIT $limit",
    ],
)
def test_validate_generated_cypher_accepts_safe_allowlisted_query(query):
    validate_generated_cypher(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) DETACH DELETE n",
        "MATCH (n:SecretLabel {workspace_id: $workspace_id}) RETURN n.id LIMIT $limit",
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) RETURN n.password LIMIT $limit",
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) RETURN n.id LIMIT $bogus",
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) RETURN n.id",
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) CALL db.labels() YIELD label RETURN label LIMIT $limit",
    ],
)
def test_validate_generated_cypher_rejects_unsafe_or_unbounded_queries(query):
    with pytest.raises(UnsafeCypherError):
        validate_generated_cypher(query)
