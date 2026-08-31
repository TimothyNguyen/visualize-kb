"""Shared management boundary for GraphRAG CLI and HTTP transports."""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Sequence

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.falkordb_adapter import FalkorDBAdapter
from kb_core_ui.rag.workspaces import RUN_CANCELLED, WorkspaceError, WorkspaceRegistry


AdapterFactory = Callable[[str], object]


class WorkspaceManager:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        config: RagConfig,
        *,
        adapter_factory: AdapterFactory | None = None,
        max_context_records: int = 200,
    ) -> None:
        if max_context_records < 1:
            raise ValueError("max_context_records must be positive")
        self.registry = registry
        self.config = config
        self.adapter_factory = adapter_factory or (
            lambda workspace_id: FalkorDBAdapter(config, workspace_id)
        )
        self.max_context_records = max_context_records

    def list_workspaces(self) -> list[dict[str, object]]:
        return [workspace.to_json_dict() for workspace in self.registry.list()]

    def create_workspace(self, workspace_id: str, name: str) -> dict[str, object]:
        return self.registry.create(workspace_id, name).to_json_dict()

    def delete_workspace(self, workspace_id: str) -> dict[str, object]:
        self.registry.mark_deleting(workspace_id)
        self._with_adapter(workspace_id, lambda adapter: adapter.delete_graph())
        self.registry.remove_workspace(workspace_id)
        return {"workspace_id": workspace_id, "deleted": True}

    def add_source(
        self, workspace_id: str, source_id: str, kind: str, uri: str, ref: str = ""
    ) -> dict[str, object]:
        source = self.registry.add_source(workspace_id, source_id, kind, uri, ref)
        return source.to_json_dict()

    def remove_source(self, workspace_id: str, source_id: str) -> dict[str, object]:
        self.registry.mark_source_deleting(workspace_id, source_id)
        self._with_adapter(workspace_id, lambda adapter: adapter.delete_source(source_id))
        self.registry.remove_source(workspace_id, source_id)
        return {"workspace_id": workspace_id, "source_id": source_id, "deleted": True}

    def start_ingestion(self, workspace_id: str, source_id: str) -> dict[str, object]:
        return self.registry.queue_run(workspace_id, source_id).to_json_dict()

    def refresh_source(self, workspace_id: str, source_id: str) -> dict[str, object]:
        return self.start_ingestion(workspace_id, source_id)

    def cancel_ingestion(self, workspace_id: str, run_id: str) -> dict[str, object]:
        return self.registry.transition_run(workspace_id, run_id, RUN_CANCELLED).to_json_dict()

    def get_run(self, workspace_id: str, run_id: str) -> dict[str, object]:
        return self.registry.get_run(workspace_id, run_id).to_json_dict()

    def health(self, workspace_id: str) -> dict[str, object]:
        self.registry.get(workspace_id)
        health = self._with_adapter(workspace_id, lambda adapter: adapter.health())
        return {"workspace_id": workspace_id, **asdict(health), "config": self.config.public_status()}

    def stats(self, workspace_id: str) -> dict[str, object]:
        self.registry.get(workspace_id)
        rows = self._with_adapter(
            workspace_id,
            lambda adapter: adapter.read_query(
                "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
                "OPTIONAL MATCH (n)-[r]->() "
                "WHERE r.workspace_id = $workspace_id "
                "RETURN count(DISTINCT n), count(DISTINCT r), collect(DISTINCT n.source_id)"
            ),
        )
        if len(rows) != 1 or len(rows[0]) != 3:
            raise WorkspaceError("unexpected graph statistics result")
        return {
            "workspace_id": workspace_id,
            "nodes": int(rows[0][0]),
            "relationships": int(rows[0][1]),
            "source_ids": sorted(str(value) for value in rows[0][2]),
        }

    def graph_context(
        self, workspace_id: str, *, source_ids: Sequence[str] = (), limit: int = 50
    ) -> dict[str, object]:
        self.registry.get(workspace_id)
        if limit < 1 or limit > self.max_context_records:
            raise WorkspaceError(
                f"context limit must be between 1 and {self.max_context_records}"
            )
        selected = sorted(set(source_ids))
        query = "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
        if selected:
            query += "WHERE n.source_id IN $source_ids "
        query += (
            "RETURN n.source_identity, n.label, n.node_type, n.source_id, n.text "
            "ORDER BY n.source_id, n.source_identity LIMIT $limit"
        )
        params: dict[str, object] = {"workspace_id": workspace_id}
        if selected:
            params["source_ids"] = selected
        params["limit"] = limit
        rows = self._with_adapter(
            workspace_id, lambda adapter: adapter.read_query(query, params)
        )
        records = [
            {
                "source_identity": str(row[0]),
                "label": str(row[1]),
                "node_type": str(row[2]),
                "source_id": str(row[3]),
                "text": str(row[4]),
            }
            for row in rows
        ]
        return {
            "workspace_id": workspace_id,
            "source_ids": selected,
            "limit": limit,
            "records": records,
        }

    def _with_adapter(self, workspace_id: str, operation):
        adapter = self.adapter_factory(workspace_id)
        try:
            return operation(adapter)
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()
