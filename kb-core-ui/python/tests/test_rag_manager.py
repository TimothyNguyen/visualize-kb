from __future__ import annotations

from dataclasses import dataclass

import pytest

from kb_core_ui.rag import RagConfig, WorkspaceError, WorkspaceManager, WorkspaceRegistry


@dataclass
class _Health:
    connected: bool = True
    graph_exists: bool = True
    graph_name: str = "kb_workspace_alpha"
    error: str = ""


class _Adapter:
    def __init__(self):
        self.deleted_graph = False
        self.deleted_sources: list[str] = []
        self.queries: list[tuple[str, dict[str, object]]] = []

    def health(self):
        return _Health()

    def delete_graph(self):
        self.deleted_graph = True

    def delete_source(self, source_id: str):
        self.deleted_sources.append(source_id)

    def read_query(self, query, params=None):
        values = dict(params or {})
        self.queries.append((query, values))
        if "count(DISTINCT n)" in query:
            return [[3, 2, ["docs", "repo"]]]
        return [["node-1", "Parser", "SYMBOL", "repo", "Parses code"]]

    def close(self):
        pass


@pytest.fixture
def manager(tmp_path):
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    adapters: dict[str, _Adapter] = {}

    def factory(workspace_id: str):
        return adapters.setdefault(workspace_id, _Adapter())

    config = RagConfig(enabled=False)
    value = WorkspaceManager(registry, config, adapter_factory=factory, max_context_records=200)
    value.adapters = adapters
    return value


def test_workspace_and_source_lifecycle(manager):
    workspace = manager.create_workspace("alpha", "Alpha")
    assert workspace["graph_name"] == "kb_workspace_alpha"
    assert [item["id"] for item in manager.list_workspaces()] == ["alpha"]

    source = manager.add_source("alpha", "repo", "local_repo", ".")
    assert source["status"] == "pending"
    assert manager.remove_source("alpha", "repo")["deleted"] is True
    assert manager.adapters["alpha"].deleted_sources == ["repo"]

    assert manager.delete_workspace("alpha")["deleted"] is True
    assert manager.adapters["alpha"].deleted_graph is True
    assert manager.list_workspaces() == []


def test_ingestion_start_refresh_cancel_and_status(manager):
    manager.create_workspace("alpha", "Alpha")
    manager.add_source("alpha", "repo", "local_repo", ".")

    run = manager.start_ingestion("alpha", "repo")
    assert run["status"] == "queued"
    assert manager.get_run("alpha", run["id"])["id"] == run["id"]
    assert manager.cancel_ingestion("alpha", run["id"])["status"] == "cancelled"

    refresh = manager.refresh_source("alpha", "repo")
    assert refresh["status"] == "queued"


def test_active_ingestion_blocks_destructive_operations(manager):
    manager.create_workspace("alpha", "Alpha")
    manager.add_source("alpha", "repo", "local_repo", ".")
    run = manager.start_ingestion("alpha", "repo")

    with pytest.raises(WorkspaceError, match="ingestion is active"):
        manager.remove_source("alpha", "repo")
    with pytest.raises(WorkspaceError, match="ingestion is active"):
        manager.delete_workspace("alpha")
    assert manager.adapters == {}

    manager.cancel_ingestion("alpha", run["id"])
    assert manager.remove_source("alpha", "repo")["deleted"] is True


def test_health_stats_and_bounded_context(manager):
    manager.create_workspace("alpha", "Alpha")
    manager.add_source("alpha", "repo", "local_repo", ".")

    assert manager.health("alpha")["connected"] is True
    assert manager.stats("alpha") == {
        "workspace_id": "alpha",
        "nodes": 3,
        "relationships": 2,
        "source_ids": ["docs", "repo"],
    }
    context = manager.graph_context("alpha", source_ids=["repo"], limit=25)
    assert context["limit"] == 25
    assert context["records"][0]["source_id"] == "repo"
    query, params = manager.adapters["alpha"].queries[-1]
    assert "$workspace_id" in query and "LIMIT $limit" in query
    assert params == {"workspace_id": "alpha", "source_ids": ["repo"], "limit": 25}

    with pytest.raises(WorkspaceError, match="between 1 and 200"):
        manager.graph_context("alpha", limit=201)
