"""Dynamic GraphRAG composition workflow for local and CI verification."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Callable

from kb_core_ui.rag import (
    FalkorDBAdapter,
    RagConfig,
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    SOURCE_READY,
    WorkspaceRegistry,
    normalize_kb_core_graph,
)

from harness.rag_fakes import InMemoryDriver

REPORT_SCHEMA_VERSION = "kb-core.rag-harness.v1"
REQUIRED_STAGES = (
    "workspace_lifecycle",
    "normalize_validate",
    "falkordb_upsert",
    "scoped_read",
    "source_delete_isolation",
    "registry_reopen",
    "graph_cleanup",
)


class WorkflowFailure(RuntimeError):
    pass


def _config(backend: str) -> RagConfig:
    values = dict(os.environ)
    values.setdefault("RAG_ENABLE", "true")
    values.setdefault("FALKORDB_URL", "falkor://127.0.0.1:6379")
    values.setdefault("RAG_LLM_PROVIDER", "harness-fake")
    values.setdefault("RAG_LLM_MODEL", "harness-fake")
    values.setdefault("RAG_EMBEDDING_MODEL", "harness-fake")
    if backend == "fake":
        values["FALKORDB_URL"] = "falkor://fake:6379"
    return RagConfig.from_env(values)


def _stage(report: dict[str, Any], name: str, fn: Callable[[], dict[str, Any]]) -> bool:
    start = time.monotonic()
    try:
        details = fn()
    except Exception as exc:
        report["stages"].append(
            {
                "name": name,
                "status": "failed",
                "duration_ms": round((time.monotonic() - start) * 1000, 3),
                "error": f"{exc.__class__.__name__}: {exc}",
            }
        )
        return False
    report["stages"].append(
        {
            "name": name,
            "status": "passed",
            "duration_ms": round((time.monotonic() - start) * 1000, 3),
            "details": details,
        }
    )
    return True


def _read_counts(adapter: FalkorDBAdapter) -> tuple[int, list[str]]:
    rows = adapter.read_query(
        "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
        "RETURN count(n), collect(DISTINCT n.source_id)"
    )
    if len(rows) != 1 or len(rows[0]) != 2:
        raise WorkflowFailure(f"unexpected count result: {rows!r}")
    return int(rows[0][0]), sorted(str(value) for value in rows[0][1])


def execute_rag_workflow(
    *, backend: str, fixture_path: Path, work_dir: Path, report_path: Path
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "backend": backend,
        "status": "running",
        "required_stages": list(REQUIRED_STAGES),
        "stages": [],
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    registry = WorkspaceRegistry(str(work_dir / "workspaces.json"))
    state: dict[str, Any] = {}
    adapter: FalkorDBAdapter | None = None

    def workspace_stage() -> dict[str, Any]:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        workspace = registry.create(fixture["workspace_id"], fixture["workspace_name"])
        runs = {}
        for source in fixture["sources"]:
            registry.add_source(
                workspace.id, source["id"], source["kind"], source["uri"], source.get("ref", "")
            )
            run = registry.queue_run(workspace.id, source["id"])
            registry.transition_run(workspace.id, run.id, RUN_RUNNING)
            runs[source["id"]] = run.id
        state.update({"fixture": fixture, "workspace": workspace, "runs": runs})
        return {"workspace_id": workspace.id, "sources": sorted(runs)}

    def normalize_stage() -> dict[str, Any]:
        envelopes = {}
        rejected = {}
        for source in state["fixture"]["sources"]:
            result = normalize_kb_core_graph(
                source["graph"],
                workspace_id=state["workspace"].id,
                source_id=source["id"],
                source_uri=source["uri"],
            )
            envelopes[source["id"]] = result.envelope
            rejected[source["id"]] = [item.reason for item in result.rejected]
        expected_rejections = state["fixture"].get("expected_rejections", {})
        if rejected != expected_rejections:
            raise WorkflowFailure(
                f"rejections differ: expected {expected_rejections!r}, got {rejected!r}"
            )
        state["envelopes"] = envelopes
        return {
            "nodes": sum(len(value.nodes) for value in envelopes.values()),
            "relationships": sum(len(value.relationships) for value in envelopes.values()),
            "rejected": rejected,
        }

    def upsert_stage() -> dict[str, Any]:
        nonlocal adapter
        driver = InMemoryDriver() if backend == "fake" else None
        adapter = FalkorDBAdapter(_config(backend), state["workspace"].id, driver=driver)
        for envelope in state["envelopes"].values():
            adapter.upsert_envelope(envelope)
        health = adapter.health()
        if not health.connected or not health.graph_exists:
            raise WorkflowFailure(f"FalkorDB unhealthy after upsert: {health!r}")
        return {"graph_name": adapter.graph_name, "health": "connected"}

    def read_stage() -> dict[str, Any]:
        assert adapter is not None
        count, source_ids = _read_counts(adapter)
        expected_count = sum(len(value.nodes) for value in state["envelopes"].values())
        expected_sources = sorted(state["envelopes"])
        if (count, source_ids) != (expected_count, expected_sources):
            raise WorkflowFailure(
                f"scoped read differs: expected {(expected_count, expected_sources)!r}, got {(count, source_ids)!r}"
            )
        return {"node_count": count, "source_ids": source_ids}

    def delete_stage() -> dict[str, Any]:
        assert adapter is not None
        deleted_source = state["fixture"]["sources"][0]["id"]
        adapter.delete_source(deleted_source)
        count, source_ids = _read_counts(adapter)
        remaining = {
            source["id"]
            for source in state["fixture"]["sources"]
            if source["id"] != deleted_source
        }
        expected_count = sum(len(state["envelopes"][source_id].nodes) for source_id in remaining)
        if count != expected_count or source_ids != sorted(remaining):
            raise WorkflowFailure(
                f"source delete leaked: expected {(expected_count, sorted(remaining))!r}, got {(count, source_ids)!r}"
            )
        return {"deleted_source": deleted_source, "remaining_nodes": count, "source_ids": source_ids}

    def reopen_stage() -> dict[str, Any]:
        for run_id in state["runs"].values():
            registry.transition_run(state["workspace"].id, run_id, RUN_SUCCEEDED)
        reopened = WorkspaceRegistry(str(work_dir / "workspaces.json")).get(state["workspace"].id)
        statuses = {source_id: source.status for source_id, source in reopened.sources.items()}
        if set(statuses.values()) != {SOURCE_READY}:
            raise WorkflowFailure(f"persisted source statuses not ready: {statuses!r}")
        return {"source_statuses": statuses}

    def cleanup_stage() -> dict[str, Any]:
        assert adapter is not None
        adapter.delete_graph()
        health = adapter.health()
        if health.graph_exists:
            raise WorkflowFailure("graph still exists after cleanup")
        adapter.close()
        return {"graph_deleted": True}

    stages = (
        ("workspace_lifecycle", workspace_stage),
        ("normalize_validate", normalize_stage),
        ("falkordb_upsert", upsert_stage),
        ("scoped_read", read_stage),
        ("source_delete_isolation", delete_stage),
        ("registry_reopen", reopen_stage),
        ("graph_cleanup", cleanup_stage),
    )
    passed = True
    for name, fn in stages:
        if not passed:
            report["stages"].append({"name": name, "status": "skipped", "duration_ms": 0})
            continue
        passed = _stage(report, name, fn)

    if not passed and state.get("runs"):
        for run_id in state["runs"].values():
            try:
                registry.transition_run(state["workspace"].id, run_id, RUN_FAILED, "harness failed")
            except Exception:
                pass
    report["status"] = "passed" if all(
        stage["status"] == "passed" for stage in report["stages"]
    ) else "failed"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def run_rag_workflow(args) -> int:
    fixture_path = Path(args.fixture).resolve()
    report_path = Path(args.report).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="kb-core-rag-harness-"))
    try:
        report = execute_rag_workflow(
            backend=args.backend,
            fixture_path=fixture_path,
            work_dir=temp_root,
            report_path=report_path,
        )
    finally:
        if not args.keep_work_dir:
            shutil.rmtree(temp_root, ignore_errors=True)
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["status"] == "passed" else 1
