from __future__ import annotations

import io
import json

import pytest

from kb_core_ui.cli.command import execute
from kb_core_ui.cli.root import build_root
from kb_core_ui.rag.seed import SeedError, load_seed_fixture, seed_workspace


class _Manager:
    def __init__(self):
        self.workspaces: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.run_counter = 0

    def list_workspaces(self):
        return list(self.workspaces.values())

    def create_workspace(self, workspace_id, name):
        self.calls.append(("create_workspace", workspace_id, name))
        if workspace_id in self.workspaces:
            raise ValueError(f"workspace {workspace_id!r} already exists")
        value = {
            "id": workspace_id,
            "name": name,
            "graph_name": f"kb_workspace_{workspace_id}",
            "sources": {},
            "runs": {},
        }
        self.workspaces[workspace_id] = value
        return value

    def delete_workspace(self, workspace_id):
        self.calls.append(("delete_workspace", workspace_id))
        self.workspaces.pop(workspace_id)
        return {"workspace_id": workspace_id, "deleted": True}

    def add_source(self, workspace_id, source_id, kind, uri, ref=""):
        self.calls.append(("add_source", workspace_id, source_id, kind, uri, ref))
        source = {"id": source_id, "workspace_id": workspace_id, "kind": kind, "uri": uri, "ref": ref}
        self.workspaces[workspace_id]["sources"][source_id] = source
        return source

    def start_ingestion(self, workspace_id, source_id):
        self.calls.append(("start_ingestion", workspace_id, source_id))
        self.run_counter += 1
        return {
            "id": f"run_{self.run_counter}",
            "workspace_id": workspace_id,
            "source_id": source_id,
            "status": "succeeded",
        }

    def refresh_source(self, workspace_id, source_id):
        self.calls.append(("refresh_source", workspace_id, source_id))
        return self.start_ingestion(workspace_id, source_id)


def _fixture(tmp_path, **overrides):
    body = {
        "workspace_id": "demo",
        "workspace_name": "Demo Workspace",
        "sources": [
            {"id": "repo", "kind": "local_repo", "uri": "repo"},
            {"id": "docs", "kind": "document_set", "uri": "docs"},
        ],
    }
    body.update(overrides)
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    (tmp_path / "repo").mkdir(exist_ok=True)
    (tmp_path / "docs").mkdir(exist_ok=True)
    return path


def test_seed_creates_workspace_sources_and_runs(tmp_path):
    path = _fixture(tmp_path)
    manager = _Manager()

    result = seed_workspace(manager, load_seed_fixture(str(path)))

    assert result["workspace_id"] == "demo" and result["created"] is True
    assert [source["id"] for source in result["sources"]] == ["repo", "docs"]
    assert [source["status"] for source in result["sources"]] == ["succeeded", "succeeded"]
    assert [source["added"] for source in result["sources"]] == [True, True]
    added = [call for call in manager.calls if call[0] == "add_source"]
    # A relative fixture URI is resolved against the fixture file, so the same
    # seed file works from the compose entrypoint, the docs, and the harness.
    assert added[0][4] == str(tmp_path / "repo")
    assert added[1][4] == str(tmp_path / "docs")


def test_seed_is_idempotent(tmp_path):
    path = _fixture(tmp_path)
    manager = _Manager()
    fixture = load_seed_fixture(str(path))

    seed_workspace(manager, fixture)
    manager.calls.clear()
    result = seed_workspace(manager, fixture)

    assert result["created"] is False
    assert [source["added"] for source in result["sources"]] == [False, False]
    names = [call[0] for call in manager.calls]
    assert names.count("refresh_source") == 2
    assert "add_source" not in names and "create_workspace" not in names


def test_seed_reset_drops_existing_workspace_first(tmp_path):
    path = _fixture(tmp_path)
    manager = _Manager()
    fixture = load_seed_fixture(str(path))

    seed_workspace(manager, fixture)
    manager.calls.clear()
    result = seed_workspace(manager, fixture, reset=True)

    assert result["reset"] is True and result["created"] is True
    assert [call[0] for call in manager.calls][:2] == ["delete_workspace", "create_workspace"]


def test_seed_reset_on_missing_workspace_is_not_an_error(tmp_path):
    path = _fixture(tmp_path)
    manager = _Manager()

    result = seed_workspace(manager, load_seed_fixture(str(path)), reset=True)

    assert result["reset"] is False and result["created"] is True


def test_seed_fixture_rejects_incomplete_definitions(tmp_path):
    with pytest.raises(SeedError):
        load_seed_fixture(str(_fixture(tmp_path, sources=[])))
    with pytest.raises(SeedError):
        load_seed_fixture(str(_fixture(tmp_path, workspace_id="")))
    with pytest.raises(SeedError):
        load_seed_fixture(str(_fixture(tmp_path, sources=[{"id": "repo", "kind": "local_repo"}])))
    with pytest.raises(SeedError):
        load_seed_fixture(str(tmp_path / "missing.json"))


def test_seed_cli_leaf_uses_the_same_manager_contract(tmp_path):
    path = _fixture(tmp_path)
    manager = _Manager()
    root = build_root(workspace_manager_factory=lambda _: manager)
    root.out = io.StringIO()
    root.err = io.StringIO()

    assert execute(root, ["workspace", "seed", "--fixture", str(path), "--repo", "."]) == 0
    seeded = json.loads(root.out.getvalue())
    assert seeded["workspace_id"] == "demo" and seeded["created"] is True

    root.out = io.StringIO()
    assert execute(root, ["workspace", "seed", "--fixture", str(path), "--reset", "--repo", "."]) == 0
    assert json.loads(root.out.getvalue())["reset"] is True


def test_seed_cli_reports_a_bad_fixture_as_an_error(tmp_path):
    root = build_root(workspace_manager_factory=lambda _: _Manager())
    root.out = io.StringIO()
    root.err = io.StringIO()

    assert execute(root, ["workspace", "seed", "--fixture", str(tmp_path / "nope.json"), "--repo", "."]) != 0
