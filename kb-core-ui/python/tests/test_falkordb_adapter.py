from __future__ import annotations

from dataclasses import dataclass

import pytest

from kb_core_ui.rag import (
    AdapterError,
    FalkorDBAdapter,
    RagConfig,
    UnsafeCypherError,
    normalize_kb_core_graph,
    validate_read_only_cypher,
)


@dataclass
class FakeResult:
    result_set: list


class FakeGraph:
    def __init__(self):
        self.writes: list[tuple[str, dict, int]] = []
        self.reads: list[tuple[str, dict, int]] = []
        self.read_results: list[list] = []
        self.query_results: list[list] = []
        self.deleted = False

    def query(self, query, params=None, timeout=None):
        self.writes.append((query, dict(params or {}), timeout))
        return FakeResult(self.query_results.pop(0) if self.query_results else [])

    def ro_query(self, query, params=None, timeout=None):
        self.reads.append((query, dict(params or {}), timeout))
        return FakeResult(self.read_results.pop(0) if self.read_results else [["ok"]])

    def delete(self):
        self.deleted = True


class FakeDriver:
    def __init__(self, *, graph_exists=False, ping_failures=0):
        self.graph = FakeGraph()
        self.graph_exists = graph_exists
        self.ping_failures = ping_failures
        self.pings = 0
        self.selected = ""
        self.closed = False

    def ping(self):
        self.pings += 1
        if self.pings <= self.ping_failures:
            raise ConnectionError("temporary")
        return True

    def list_graphs(self):
        return [self.selected] if self.graph_exists else []

    def select_graph(self, graph_name):
        self.selected = graph_name
        return self.graph

    def close(self):
        self.closed = True


def config() -> RagConfig:
    return RagConfig.from_env(
        {
            "RAG_ENABLE": "true",
            "FALKORDB_URL": "falkor://localhost:6379",
            "RAG_LLM_PROVIDER": "fake",
            "RAG_LLM_MODEL": "fake",
            "RAG_EMBEDDING_MODEL": "fake",
            "RAG_QUERY_TIMEOUT_SECONDS": "7",
        }
    )


def envelope(workspace_id="alpha"):
    return normalize_kb_core_graph(
        {
            "nodes": [
                {
                    "id": "src/api.py:Api",
                    "label": "Api",
                    "source_location": "src/api.py:L1",
                    "doc": "API entrypoint.",
                },
                {
                    "id": "src/store.py:Store",
                    "label": "Store",
                    "source_location": "src/store.py:L1",
                    "doc": "Persists data.",
                },
            ],
            "links": [
                {
                    "source": "src/api.py:Api",
                    "target": "src/store.py:Store",
                    "relation": "calls",
                }
            ],
        },
        workspace_id=workspace_id,
        source_id="repo",
    ).envelope


def test_health_retries_transient_failure_and_reports_graph() -> None:
    driver = FakeDriver(graph_exists=True, ping_failures=1)
    sleeps = []
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver, sleep=sleeps.append)

    health = adapter.health()

    assert health.connected is True
    assert health.graph_exists is True
    assert health.graph_name == "kb_workspace_alpha"
    assert driver.pings == 2
    assert sleeps == [0.05]


def test_upsert_uses_fixed_schema_parameterized_rows_and_timeout() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter.upsert_envelope(envelope())

    assert len(driver.graph.writes) == 5
    assert all(timeout == 7_000 for _, _, timeout in driver.graph.writes)
    assert all(params["workspace_id"] == "alpha" for _, params, _ in driver.graph.writes)
    queries = "\n".join(query for query, _, _ in driver.graph.writes)
    assert ":KnowledgeNode" in queries
    assert ":RELATED" in queries
    assert ":TextChunk" in queries
    assert ":Citation" in queries
    assert "CALLS" not in queries


def test_batched_write_limits_each_transaction_to_500_rows() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter._write_rows(
        "WITH $workspace_id AS workspace_id UNWIND $rows AS row RETURN row, workspace_id",
        {"workspace_id": "alpha", "rows": [{"id": index} for index in range(1001)]},
    )

    assert [len(params["rows"]) for _, params, _ in driver.graph.writes] == [500, 500, 1]


def test_ingestion_lookup_index_is_created_only_when_missing() -> None:
    existing = FakeDriver()
    existing.graph.query_results = [[["KnowledgeNode", ["id"]]]]
    FalkorDBAdapter(config(), "alpha", driver=existing)._ensure_ingestion_indexes()
    assert len(existing.graph.writes) == 1

    missing = FakeDriver()
    missing.graph.query_results = [[]]
    FalkorDBAdapter(config(), "alpha", driver=missing)._ensure_ingestion_indexes()
    assert len(missing.graph.writes) == 2
    assert missing.graph.writes[1][0] == "CREATE INDEX FOR (n:KnowledgeNode) ON (n.id)"


def test_adapter_rejects_cross_workspace_envelope_and_parameter() -> None:
    adapter = FalkorDBAdapter(config(), "alpha", driver=FakeDriver())

    with pytest.raises(AdapterError, match="does not match adapter workspace"):
        adapter.upsert_envelope(envelope("beta"))
    with pytest.raises(AdapterError, match="does not match adapter workspace"):
        adapter.read_query(
            "MATCH (n {workspace_id: $workspace_id}) RETURN n", {"workspace_id": "beta"}
        )


def test_read_query_is_read_only_scoped_and_bounded() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    rows = adapter.read_query(
        "MATCH (n {workspace_id: $workspace_id}) WHERE n.label = $label RETURN n LIMIT 5",
        {"label": "Api"},
    )

    assert rows == [["ok"]]
    query, params, timeout = driver.graph.reads[0]
    assert query.startswith("MATCH")
    assert params == {"label": "Api", "workspace_id": "alpha"}
    assert timeout == 7_000


@pytest.mark.parametrize(
    "query, message",
    [
        ("MATCH (n) DELETE n", "write clause DELETE"),
        ("MATCH (n) SET n.x = 1 RETURN n", "write clause SET"),
        ("CALL db.labels() YIELD label RETURN label", "CALL is not allowed"),
        ("MATCH (n) RETURN n; MATCH (m) RETURN m", "multiple Cypher statements"),
        ("MATCH (n) RETURN n", "must scope records"),
    ],
)
def test_read_only_validator_rejects_unsafe_queries(query, message) -> None:
    with pytest.raises(UnsafeCypherError, match=message):
        validate_read_only_cypher(query)


def test_validator_ignores_keywords_inside_literals_and_comments() -> None:
    validate_read_only_cypher(
        "MATCH (n {workspace_id: $workspace_id}) "
        "WHERE n.text = 'DELETE SET' // CREATE is text\n"
        "RETURN n"
    )


def test_delete_source_and_graph_stay_bound_to_selected_workspace() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter.delete_source("repo")
    adapter.delete_graph()

    assert len(driver.graph.writes) == 2
    assert all(
        params == {"workspace_id": "alpha", "source_id": "repo"}
        for _, params, _ in driver.graph.writes
    )
    assert driver.graph.deleted is True


def test_adapter_requires_ready_config_without_importing_optional_driver() -> None:
    with pytest.raises(AdapterError, match="RAG_ENABLE=true"):
        FalkorDBAdapter(RagConfig.from_env({}), "alpha")


def test_stage_envelope_writes_inactive_versioned_records() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter.stage_envelope(envelope(), "version-next")

    assert len(driver.graph.writes) == 5
    record_writes = driver.graph.writes[1:]
    assert all(params["version"] == "version-next" for _, params, _ in record_writes)
    assert all("active = false" in query for query, _, _ in record_writes)
    assert all("ingestion_version" in query for query, _, _ in record_writes)


def test_manifest_and_stage_counts_are_source_scoped() -> None:
    driver = FakeDriver(graph_exists=True)
    driver.graph.read_results = [
        [["version-old", "hash-old", "extractor-old"]],
        [[2]],
        [[1]],
        [[2]],
        [[2]],
    ]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    manifest = adapter.get_source_manifest("repo")
    counts = adapter.verify_source_stage("repo", "version-next")

    assert manifest.active_version == "version-old"
    assert manifest.content_hash == "hash-old"
    assert counts.nodes == 2
    assert counts.relationships == 1
    assert counts.chunks == 2
    assert counts.citations == 2
    assert all(read[1]["source_id"] == "repo" for read in driver.graph.reads)
    relationship_count_query = driver.graph.reads[2][0]
    assert "]->()" in relationship_count_query


def test_manifest_is_absent_before_workspace_graph_exists() -> None:
    driver = FakeDriver(graph_exists=False)
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    assert adapter.get_source_manifest("repo") is None
    assert driver.graph.reads == []


def test_publish_is_one_atomic_swap_and_recovery_is_source_owned() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter.publish_source_stage("repo", "version-next", "hash-next", "extractor-next")
    adapter.recover_source("repo", "version-old")
    adapter.rollback_source_stage("repo", "version-next")

    publish_query, publish_params, _ = driver.graph.writes[0]
    assert "active_version" in publish_query
    assert "DETACH DELETE" in publish_query
    assert publish_params == {
        "workspace_id": "alpha",
        "source_id": "repo",
        "version": "version-next",
        "content_hash": "hash-next",
        "extractor_version": "extractor-next",
    }
    assert all(
        params["workspace_id"] == "alpha" and params["source_id"] == "repo"
        for _, params, _ in driver.graph.writes
    )
    rollback_queries = [query for query, _, _ in driver.graph.writes[-3:]]
    assert "DELETE r" in rollback_queries[0]
    assert "DETACH DELETE n" in rollback_queries[1]
    assert "stage_status = 'rolled_back'" in rollback_queries[2]


def test_embedding_writes_target_exact_staged_version() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)
    value = envelope()

    adapter.write_embeddings(
        value,
        "version-next",
        [{"id": chunk.id, "embedding": [1.0, 0.0]} for chunk in value.chunks],
        [
            {"id": node.id, "embedding": [0.0, 1.0], "embedding_text": node.label}
            for node in value.nodes
        ],
    )

    assert len(driver.graph.writes) == 2
    assert all("ingestion_version: $version" in query for query, _, _ in driver.graph.writes)
    assert all("vecf32(row.embedding)" in query for query, _, _ in driver.graph.writes)
    assert all(params["version"] == "version-next" for _, params, _ in driver.graph.writes)


def test_ensure_retrieval_indexes_creates_and_verifies_four_indexes() -> None:
    driver = FakeDriver(graph_exists=True)
    driver.graph.read_results = [[]]
    driver.graph.query_results = [
        [],
        [],
        [],
        [],
        [],
        [
            ["TextChunk", ["text", "embedding"], {"text": ["FULLTEXT"], "embedding": ["VECTOR"]}, "OPERATIONAL"],
            [
                "KnowledgeNode",
                ["label", "text", "embedding"],
                {"label": ["FULLTEXT"], "text": ["FULLTEXT"], "embedding": ["VECTOR"]},
                "OPERATIONAL",
            ],
        ],
    ]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    count = adapter.ensure_retrieval_indexes(3, "kb-core.retrieval.v1")

    assert count == 4
    queries = "\n".join(query for query, _, _ in driver.graph.writes)
    assert "CREATE FULLTEXT INDEX FOR (n:TextChunk) ON (n.text)" in queries
    assert "CREATE FULLTEXT INDEX FOR (n:KnowledgeNode) ON (n.label, n.text)" in queries
    assert "CREATE VECTOR INDEX FOR (n:TextChunk) ON (n.embedding)" in queries
    assert "dimension: 3" in queries
    assert "MERGE (m:IndexManifest" in queries
    assert "CALL db.indexes()" in queries


def test_ensure_retrieval_indexes_waits_for_async_index_build() -> None:
    driver = FakeDriver(graph_exists=True)
    driver.graph.read_results = [[['kb-core.retrieval.v1', 3]]]
    under_construction = [
        ["KnowledgeNode", ["embedding"], {"embedding": ["VECTOR"]}, "UNDER CONSTRUCTION"]
    ]
    operational = [
        ["TextChunk", ["text", "embedding"], {"text": ["FULLTEXT"], "embedding": ["VECTOR"]}, "OPERATIONAL"],
        ["KnowledgeNode", ["label", "text", "embedding"], {"label": ["FULLTEXT"], "text": ["FULLTEXT"], "embedding": ["VECTOR"]}, "OPERATIONAL"],
    ]
    driver.graph.query_results = [under_construction, operational]
    sleeps = []
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver, sleep=sleeps.append)

    assert adapter.ensure_retrieval_indexes(3, "kb-core.retrieval.v1") == 4
    assert sleeps == [0.25]


def test_write_chat_turn_is_single_scoped_write_returning_sequence() -> None:
    driver = FakeDriver()
    driver.graph.query_results = [[[3]]]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    seq = adapter.write_chat_turn(
        "alpha::conv-1", "conv-1", "turn-1", "what parses records?", "{}", "2026-08-31T00:00:00Z"
    )

    assert seq == 3
    assert len(driver.graph.writes) == 1
    query, params, timeout = driver.graph.writes[0]
    assert ":ChatThread" in query and ":ChatTurn" in query
    assert "$workspace_id" in query
    assert params == {
        "workspace_id": "alpha",
        "thread_key": "alpha::conv-1",
        "thread_id": "conv-1",
        "turn_id": "turn-1",
        "query_text": "what parses records?",
        "response_json": "{}",
        "created_at": "2026-08-31T00:00:00Z",
    }
    assert timeout == 7_000


def test_list_chat_turns_reads_only_and_scoped_to_thread_key() -> None:
    driver = FakeDriver()
    driver.graph.read_results = [
        [["turn-1", 1, "q1", "{}", "2026-08-31T00:00:00Z"]],
    ]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    rows = adapter.list_chat_turns("alpha::conv-1")

    assert rows == [["turn-1", 1, "q1", "{}", "2026-08-31T00:00:00Z"]]
    query, params, _ = driver.graph.reads[0]
    assert "ChatTurn" in query
    assert params == {"workspace_id": "alpha", "thread_key": "alpha::conv-1"}


def test_trim_and_delete_chat_thread_stay_scoped_to_workspace_and_thread() -> None:
    driver = FakeDriver()
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    adapter.trim_chat_turns("alpha::conv-1", 2)
    adapter.delete_chat_thread("alpha::conv-1")

    assert len(driver.graph.writes) == 3
    assert all(params["workspace_id"] == "alpha" for _, params, _ in driver.graph.writes)
    assert all(params["thread_key"] == "alpha::conv-1" for _, params, _ in driver.graph.writes)
    trim_query = driver.graph.writes[0][0]
    assert "cutoff_seq" in trim_query


def test_delete_all_chat_threads_counts_then_deletes_workspace_scoped_only() -> None:
    driver = FakeDriver()
    driver.graph.read_results = [[[2]]]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    count = adapter.delete_all_chat_threads()

    assert count == 2
    assert len(driver.graph.writes) == 2
    assert all(params == {"workspace_id": "alpha"} for _, params, _ in driver.graph.writes)


def test_search_methods_parameterize_scope_and_return_candidates() -> None:
    driver = FakeDriver(graph_exists=True)
    driver.graph.query_results = [
        [["chunk-a", "repo", "chunk text", "a.md", 4.0, "chunk"]],
        [["node-a", "repo", "node text", "a.py", 3.0, "node"]],
        [["chunk-a", "repo", "chunk text", "a.md", 0.9, "chunk"]],
        [["node-a", "repo", "node text", "a.py", 0.8, "node"]],
    ]
    adapter = FalkorDBAdapter(config(), "alpha", driver=driver)

    lexical = adapter.fulltext_search("graph", 5, ("repo",))
    vector = adapter.vector_search([1.0, 0.0], 5, ("repo",))

    assert [candidate.id for candidate in lexical] == ["chunk-a", "node-a"]
    assert [candidate.id for candidate in vector] == ["chunk-a", "node-a"]
    assert all(params["workspace_id"] == "alpha" for _, params, _ in driver.graph.writes)
    assert all(params["source_ids"] == ["repo"] for _, params, _ in driver.graph.writes)
    assert all("$workspace_id" in query and "$source_ids" in query for query, _, _ in driver.graph.writes)
