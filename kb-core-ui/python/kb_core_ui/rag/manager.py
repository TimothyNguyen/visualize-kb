"""Shared management boundary for GraphRAG CLI and HTTP transports."""

from __future__ import annotations

import sys
from dataclasses import asdict
from typing import Callable, Sequence

from kb_core_ui.rag.chat_memory import ChatMemorySink, NullChatMemorySink
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
        ingestion_coordinator: object | None = None,
        chat_memory_sink: ChatMemorySink | None = None,
        max_context_records: int = 200,
    ) -> None:
        if max_context_records < 1:
            raise ValueError("max_context_records must be positive")
        self.registry = registry
        self.config = config
        self.adapter_factory = adapter_factory or (
            lambda workspace_id: FalkorDBAdapter(config, workspace_id)
        )
        self.ingestion_coordinator = ingestion_coordinator
        self.chat_memory_sink = chat_memory_sink or NullChatMemorySink()
        self.max_context_records = max_context_records

    def list_workspaces(self) -> list[dict[str, object]]:
        return [workspace.to_json_dict() for workspace in self.registry.list()]

    def create_workspace(self, workspace_id: str, name: str) -> dict[str, object]:
        return self.registry.create(workspace_id, name).to_json_dict()

    def delete_workspace(self, workspace_id: str) -> dict[str, object]:
        self.registry.mark_deleting(workspace_id)
        self._with_adapter(workspace_id, lambda adapter: adapter.delete_graph())
        # The chat archive lives outside the graph, so dropping the graph does
        # not reach it. Without this the workspace disappears while its turns
        # stay searchable.
        try:
            self.chat_memory_sink.delete_workspace(workspace_id)
        except Exception as exc:  # noqa: BLE001 - a broken archive cannot block a delete
            print(f"chat memory delete_workspace failed: {exc}", file=sys.stderr)
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
        run = self.registry.queue_run(workspace_id, source_id)
        if self.ingestion_coordinator is None:
            return run.to_json_dict()
        return self.ingestion_coordinator.execute(workspace_id, source_id, run.id)

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
        self,
        workspace_id: str,
        *,
        source_ids: Sequence[str] = (),
        limit: int = 50,
        focus: str = "",
    ) -> dict[str, object]:
        """Nodes plus the relationships between them, so a caller can draw the
        workspace graph. ``focus`` narrows both to the neighbourhood of one
        node identity, which is the bounded subgraph a citation opens."""
        self.registry.get(workspace_id)
        if limit < 1 or limit > self.max_context_records:
            raise WorkspaceError(
                f"context limit must be between 1 and {self.max_context_records}"
            )
        selected = sorted(set(source_ids))

        edge_query = (
            "MATCH (a:KnowledgeNode {workspace_id: $workspace_id})"
            "-[r:RELATED {workspace_id: $workspace_id}]->"
            "(b:KnowledgeNode {workspace_id: $workspace_id}) "
        )
        edge_filters = []
        edge_params: dict[str, object] = {"workspace_id": workspace_id}
        if selected:
            edge_filters.append("r.source_id IN $source_ids")
            edge_params["source_ids"] = selected
        if focus:
            edge_filters.append("(a.source_identity = $focus OR b.source_identity = $focus)")
            edge_params["focus"] = focus
        if edge_filters:
            edge_query += "WHERE " + " AND ".join(edge_filters) + " "
        edge_query += (
            "RETURN a.source_identity, b.source_identity, r.relationship_type, r.source_id "
            "ORDER BY a.source_identity, b.source_identity LIMIT $limit"
        )
        edge_params["limit"] = limit

        node_params: dict[str, object] = {"workspace_id": workspace_id}
        if focus:
            node_query = (
                "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
                "WHERE n.source_identity IN $identities "
                "RETURN n.source_identity, n.label, n.node_type, n.source_id, n.text, "
                "n.source_location "
                "ORDER BY n.source_id, n.source_identity LIMIT $limit"
            )
        else:
            node_query = "MATCH (n:KnowledgeNode {workspace_id: $workspace_id}) "
            if selected:
                node_query += "WHERE n.source_id IN $source_ids "
                node_params["source_ids"] = selected
            node_query += (
                "RETURN n.source_identity, n.label, n.node_type, n.source_id, n.text, "
                "n.source_location "
                "ORDER BY n.source_id, n.source_identity LIMIT $limit"
            )
        node_params["limit"] = limit

        def read(adapter):
            edge_rows = adapter.read_query(edge_query, edge_params)
            if focus:
                identities = {focus}
                for row in edge_rows:
                    identities.update({str(row[0]), str(row[1])})
                node_params["identities"] = sorted(identities)
            return edge_rows, adapter.read_query(node_query, node_params)

        edge_rows, node_rows = self._with_adapter(workspace_id, read)
        return {
            "workspace_id": workspace_id,
            "source_ids": selected,
            "limit": limit,
            "focus": focus,
            "records": [
                {
                    "source_identity": str(row[0]),
                    "label": str(row[1]),
                    "node_type": str(row[2]),
                    "source_id": str(row[3]),
                    "text": str(row[4]),
                    "source_location": str(row[5]),
                }
                for row in node_rows
            ],
            "edges": [
                {
                    "source": str(row[0]),
                    "target": str(row[1]),
                    "relation": str(row[2]),
                    "source_id": str(row[3]),
                }
                for row in edge_rows
            ],
        }

    def _with_adapter(self, workspace_id: str, operation):
        adapter = self.adapter_factory(workspace_id)
        try:
            return operation(adapter)
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()
