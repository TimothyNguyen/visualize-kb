from __future__ import annotations

import json

import pytest

from kb_core_ui.config import default_db_path, workspace_registry_path
from kb_core_ui.rag import (
    RUN_CANCELLED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    SOURCE_DELETING,
    SOURCE_PENDING,
    SOURCE_READY,
    WORKSPACE_DELETING,
    WorkspaceError,
    WorkspaceRegistry,
    workspace_graph_name,
)


def test_workspace_registry_persists_sources_and_safe_graph_name(tmp_path) -> None:
    path = workspace_registry_path(str(tmp_path))
    registry = WorkspaceRegistry(path)
    workspace = registry.create("platform-docs", "Platform Docs")
    source = registry.add_source(
        workspace.id,
        "api-repo",
        "github_repo",
        "https://github.com/acme/api",
        "main",
    )

    reopened = WorkspaceRegistry(path).get("platform-docs")
    assert workspace.graph_name == "kb_workspace_platform_docs"
    assert reopened.sources["api-repo"].workspace_id == "platform-docs"
    assert reopened.sources["api-repo"].uri == source.uri
    assert default_db_path(str(tmp_path)).endswith("graph.db")
    assert path.endswith("workspaces.json")


def test_workspace_and_source_ids_reject_graph_name_injection(tmp_path) -> None:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))

    with pytest.raises(WorkspaceError, match="workspace id must start"):
        registry.create("x) MATCH (n) DELETE n", "unsafe")
    with pytest.raises(WorkspaceError, match="workspace id must start"):
        workspace_graph_name("other_workspace")


def test_run_lifecycle_is_scoped_and_persisted(tmp_path) -> None:
    path = str(tmp_path / "workspaces.json")
    registry = WorkspaceRegistry(path)
    registry.create("alpha", "Alpha")
    registry.create("beta", "Beta")
    registry.add_source("alpha", "repo", "local_repo", "C:/src/alpha")
    registry.add_source("beta", "repo", "local_repo", "C:/src/beta")

    run = registry.queue_run("alpha", "repo")
    registry.transition_run("alpha", run.id, RUN_RUNNING)
    registry.transition_run("alpha", run.id, RUN_SUCCEEDED)

    alpha = WorkspaceRegistry(path).get("alpha")
    beta = WorkspaceRegistry(path).get("beta")
    assert alpha.sources["repo"].status == SOURCE_READY
    assert alpha.runs[run.id].status == RUN_SUCCEEDED
    assert beta.sources["repo"].status == SOURCE_PENDING
    with pytest.raises(WorkspaceError, match="does not exist in workspace 'beta'"):
        registry.transition_run("beta", run.id, RUN_CANCELLED)


def test_terminal_run_cannot_restart_and_deleting_source_cannot_queue(tmp_path) -> None:
    registry = WorkspaceRegistry(str(tmp_path / "workspaces.json"))
    registry.create("alpha", "Alpha")
    registry.add_source("alpha", "repo", "local_repo", "C:/src/alpha")
    run = registry.queue_run("alpha", "repo")
    registry.transition_run("alpha", run.id, RUN_CANCELLED)

    with pytest.raises(WorkspaceError, match="cannot transition"):
        registry.transition_run("alpha", run.id, RUN_RUNNING)
    assert registry.mark_source_deleting("alpha", "repo").status == SOURCE_DELETING
    with pytest.raises(WorkspaceError, match="must be active"):
        registry.queue_run("alpha", "repo")


def test_workspace_delete_is_lifecycle_state_not_immediate_data_loss(tmp_path) -> None:
    path = str(tmp_path / "workspaces.json")
    registry = WorkspaceRegistry(path)
    registry.create("alpha", "Alpha")
    registry.add_source("alpha", "repo", "local_repo", "C:/src/alpha")

    registry.mark_deleting("alpha")

    persisted = json.loads((tmp_path / "workspaces.json").read_text(encoding="utf-8"))
    assert persisted["workspaces"]["alpha"]["status"] == WORKSPACE_DELETING
    assert "repo" in persisted["workspaces"]["alpha"]["sources"]
    with pytest.raises(WorkspaceError, match="not active"):
        registry.add_source("alpha", "other", "local_repo", "C:/src/other")
