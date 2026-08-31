"""Semantic in-memory FalkorDB fake used by dynamic RAG harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class FakeResult:
    result_set: list[list[Any]]


class InMemoryGraph:
    def __init__(self, driver: "InMemoryDriver", name: str):
        self.driver = driver
        self.name = name
        self.workspace_meta: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.relationships: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, dict[str, Any]] = {}
        self.citations: dict[str, dict[str, Any]] = {}

    def query(self, query: str, params: Mapping[str, object] | None = None, timeout=None):
        values = dict(params or {})
        self.driver.existing.add(self.name)
        if "MERGE (m:WorkspaceMeta" in query:
            workspace_id = str(values["workspace_id"])
            self.workspace_meta[workspace_id] = values
        elif "MERGE (n:KnowledgeNode" in query:
            for row in values.get("rows", []):
                self.nodes[str(row["id"])] = dict(row)
        elif "MERGE (a)-[r:RELATED" in query:
            for row in values.get("rows", []):
                if row["source"] not in self.nodes or row["target"] not in self.nodes:
                    raise RuntimeError("relationship endpoint missing")
                self.relationships[str(row["id"])] = dict(row)
        elif "MERGE (c:TextChunk" in query:
            for row in values.get("rows", []):
                self.chunks[str(row["id"])] = dict(row)
        elif "MERGE (c:Citation" in query:
            for row in values.get("rows", []):
                self.citations[str(row["id"])] = dict(row)
        elif "MATCH ()-[r:RELATED" in query:
            self._delete_owned(self.relationships, values)
        elif "DETACH DELETE n" in query:
            self._delete_owned(self.nodes, values)
            self._delete_owned(self.chunks, values)
            self._delete_owned(self.citations, values)
            live_nodes = set(self.nodes)
            self.relationships = {
                key: row
                for key, row in self.relationships.items()
                if row["source"] in live_nodes and row["target"] in live_nodes
            }
        else:
            raise RuntimeError(f"fake does not implement query: {query}")
        return FakeResult([])

    @staticmethod
    def _delete_owned(records: dict[str, dict[str, Any]], values: Mapping[str, object]) -> None:
        workspace_id = values["workspace_id"]
        source_id = values["source_id"]
        for key in [
            key
            for key, row in records.items()
            if row.get("workspace_id") == workspace_id and row.get("source_id") == source_id
        ]:
            del records[key]

    def ro_query(self, query: str, params: Mapping[str, object] | None = None, timeout=None):
        values = dict(params or {})
        if "count(n)" not in query or "collect(DISTINCT n.source_id)" not in query:
            raise RuntimeError(f"fake does not implement read query: {query}")
        workspace_id = values["workspace_id"]
        rows = [row for row in self.nodes.values() if row["workspace_id"] == workspace_id]
        return FakeResult([[len(rows), sorted({row["source_id"] for row in rows})]])

    def delete(self):
        self.driver.graphs.pop(self.name, None)
        self.driver.existing.discard(self.name)


class InMemoryDriver:
    def __init__(self):
        self.graphs: dict[str, InMemoryGraph] = {}
        self.existing: set[str] = set()
        self.closed = False

    def ping(self) -> bool:
        return True

    def list_graphs(self):
        return sorted(self.existing)

    def select_graph(self, graph_name: str):
        if graph_name not in self.graphs:
            self.graphs[graph_name] = InMemoryGraph(self, graph_name)
        return self.graphs[graph_name]

    def close(self):
        self.closed = True
