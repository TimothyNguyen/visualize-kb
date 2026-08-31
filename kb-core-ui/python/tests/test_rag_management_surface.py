from __future__ import annotations

import io
import json

from kb_core_ui.cli.command import execute
from kb_core_ui.cli.root import build_root
from kb_core_ui.server import Server
from kb_core_ui.store import Store

from test_server import request


class _Manager:
    def __init__(self):
        self.workspaces: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}

    def list_workspaces(self):
        return list(self.workspaces.values())

    def create_workspace(self, workspace_id, name):
        value = {"id": workspace_id, "name": name, "graph_name": f"kb_workspace_{workspace_id}"}
        self.workspaces[workspace_id] = value
        return value

    def delete_workspace(self, workspace_id):
        self.workspaces.pop(workspace_id)
        return {"workspace_id": workspace_id, "deleted": True}

    def add_source(self, workspace_id, source_id, kind, uri, ref=""):
        return {"id": source_id, "workspace_id": workspace_id, "kind": kind, "uri": uri, "ref": ref}

    def remove_source(self, workspace_id, source_id):
        return {"workspace_id": workspace_id, "source_id": source_id, "deleted": True}

    def start_ingestion(self, workspace_id, source_id):
        run = {"id": "run_1", "workspace_id": workspace_id, "source_id": source_id, "status": "queued"}
        self.runs[run["id"]] = run
        return run

    refresh_source = start_ingestion

    def cancel_ingestion(self, workspace_id, run_id):
        self.runs[run_id]["status"] = "cancelled"
        return self.runs[run_id]

    def get_run(self, workspace_id, run_id):
        return self.runs[run_id]

    def health(self, workspace_id):
        return {"workspace_id": workspace_id, "connected": True}

    def stats(self, workspace_id):
        return {"workspace_id": workspace_id, "nodes": 3, "relationships": 2, "source_ids": ["repo"]}

    def graph_context(self, workspace_id, source_ids=(), limit=50):
        return {"workspace_id": workspace_id, "limit": limit, "source_ids": list(source_ids), "records": []}


def test_workspace_http_resource_contract(tmp_path):
    manager = _Manager()
    with Store(str(tmp_path / "graph.db")) as store:
        app = Server(store, str(tmp_path), workspace_manager=manager)
        status, workspace, _ = request(
            app, "POST", "/api/rag/workspaces", json.dumps({"id": "alpha", "name": "Alpha"}).encode()
        )
        assert status == 201 and workspace["id"] == "alpha"
        assert request(app, "GET", "/api/rag/workspaces")[1][0]["id"] == "alpha"

        target = "/api/rag/workspaces/alpha/sources"
        status, source, _ = request(
            app, "POST", target, json.dumps({"id": "repo", "kind": "local_repo", "uri": "."}).encode()
        )
        assert status == 201 and source["id"] == "repo"

        status, run, _ = request(app, "POST", target + "/repo/ingestions", b"{}")
        assert status == 202 and run["status"] == "queued"
        assert request(app, "GET", "/api/rag/workspaces/alpha/runs/run_1")[1]["id"] == "run_1"
        assert request(app, "POST", "/api/rag/workspaces/alpha/runs/run_1/cancel", b"{}")[1]["status"] == "cancelled"
        assert request(app, "GET", "/api/rag/workspaces/alpha/context?limit=20&source=repo")[1]["limit"] == 20


def test_workspace_cli_uses_same_manager_contract():
    manager = _Manager()
    root = build_root(workspace_manager_factory=lambda _: manager)
    root.out = io.StringIO()
    root.err = io.StringIO()

    assert execute(root, ["workspace", "create", "alpha", "--name", "Alpha", "--repo", "."]) == 0
    created = json.loads(root.out.getvalue())
    assert created["id"] == "alpha"

    root.out = io.StringIO()
    assert execute(root, ["workspace", "list", "--repo", "."]) == 0
    assert json.loads(root.out.getvalue())[0]["name"] == "Alpha"
