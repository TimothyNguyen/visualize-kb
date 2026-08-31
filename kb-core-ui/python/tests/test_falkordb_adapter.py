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
        self.deleted = False

    def query(self, query, params=None, timeout=None):
        self.writes.append((query, dict(params or {}), timeout))
        return FakeResult([])

    def ro_query(self, query, params=None, timeout=None):
        self.reads.append((query, dict(params or {}), timeout))
        return FakeResult([["ok"]])

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
