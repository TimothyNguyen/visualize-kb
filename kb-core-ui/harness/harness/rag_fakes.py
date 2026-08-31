"""Semantic in-memory FalkorDB fake used by dynamic RAG harness."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


@dataclass
class FakeResult:
    result_set: list[list[Any]]


class InMemoryGraph:
    def __init__(self, driver: "InMemoryDriver", name: str):
        self.driver = driver
        self.name = name
        self.workspace_meta: dict[str, dict[str, Any]] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.relationships: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, dict[str, Any]] = {}
        self.citations: dict[str, dict[str, Any]] = {}
        self.index_manifest: dict[str, Any] | None = None
        self.indexes: set[tuple[str, str, str]] = set()

    @staticmethod
    def _key(row: Mapping[str, Any], values: Mapping[str, object]) -> str:
        return f"{row['id']}::{values.get('version', '')}"

    def query(self, query: str, params: Mapping[str, object] | None = None, timeout=None):
        values = dict(params or {})
        self.driver.existing.add(self.name)
        if "MERGE (m:WorkspaceMeta" in query:
            self.workspace_meta[str(values["workspace_id"])] = values
        elif "MERGE (m:SourceManifest" in query:
            source_id = str(values["source_id"])
            manifest = self.manifests.setdefault(source_id, {"source_id": source_id})
            manifest.update(
                staging_version=values["version"],
                staging_content_hash=values["content_hash"],
                staging_extractor_version=values["extractor_version"],
                stage_status="writing",
            )
        elif "RETURN m.active_version" in query:
            self._publish(values)
        elif "SET c.embedding = vecf32" in query:
            self._write_embeddings(self.chunks, values)
        elif "SET n.embedding = vecf32" in query:
            self._write_embeddings(self.nodes, values)
        elif "MERGE (m:IndexManifest" in query:
            self.index_manifest = {
                "index_version": values["index_version"],
                "dimension": values["dimension"],
            }
        elif query.startswith("CREATE FULLTEXT INDEX"):
            label = "TextChunk" if "TextChunk" in query else "KnowledgeNode"
            self.indexes.add((label, "text", "FULLTEXT"))
            if label == "KnowledgeNode":
                self.indexes.add((label, "label", "FULLTEXT"))
        elif query.startswith("CREATE VECTOR INDEX"):
            label = "TextChunk" if "TextChunk" in query else "KnowledgeNode"
            self.indexes.add((label, "embedding", "VECTOR"))
        elif query.startswith("DROP INDEX"):
            label = "TextChunk" if "TextChunk" in query else "KnowledgeNode"
            self.indexes.discard((label, "embedding", "VECTOR"))
        elif query.startswith("CALL db.indexes()"):
            return FakeResult([[label, [prop], [kind], "OPERATIONAL"] for label, prop, kind in self.indexes])
        elif query.startswith("CALL db.idx.fulltext.queryNodes"):
            return FakeResult(self._fulltext(query, values))
        elif query.startswith("CALL db.idx.vector.queryNodes"):
            return FakeResult(self._vector(query, values))
        elif "MERGE (n:KnowledgeNode" in query:
            self._store(self.nodes, values, active="active = false" not in query)
        elif "MERGE (a)-[r:RELATED" in query:
            self._store(self.relationships, values, active="active = false" not in query)
        elif "MERGE (c:TextChunk" in query:
            self._store(self.chunks, values, active="active = false" not in query)
        elif "MERGE (c:Citation" in query:
            self._store(self.citations, values, active="active = false" not in query)
        elif "MATCH ()-[r:RELATED" in query:
            self._delete_owned(self.relationships, values, query)
        elif "DETACH DELETE n" in query:
            for records in (self.nodes, self.chunks, self.citations):
                self._delete_owned(records, values, query)
            if "version" not in values and "active_version" not in values:
                self.manifests.pop(str(values["source_id"]), None)
        elif "MATCH (m:SourceManifest" in query:
            manifest = self.manifests.get(str(values["source_id"]))
            if manifest is not None:
                manifest.update(
                    staging_version=None,
                    staging_content_hash=None,
                    staging_extractor_version=None,
                    stage_status="rolled_back" if "rolled_back" in query else "recovered",
                )
        else:
            raise RuntimeError(f"fake does not implement query: {query}")
        return FakeResult([])

    def _write_embeddings(
        self, records: dict[str, dict[str, Any]], values: Mapping[str, object]
    ) -> None:
        rows = {str(row["id"]): row for row in values["rows"]}
        for record in records.values():
            row = rows.get(str(record["id"]))
            if (
                row is not None
                and record.get("source_id") == values["source_id"]
                and record.get("ingestion_version") == values["version"]
            ):
                record["embedding"] = list(row["embedding"])
                if "embedding_text" in row:
                    record["embedding_text"] = row["embedding_text"]

    def _search_records(self, query: str, values: Mapping[str, object]):
        records = self.chunks if "TextChunk" in query else self.nodes
        source_ids = set(values.get("source_ids", []))
        return [
            row
            for row in records.values()
            if row.get("workspace_id") == values["workspace_id"]
            and row.get("active", True)
            and (not source_ids or row.get("source_id") in source_ids)
        ]

    def _fulltext(self, query: str, values: Mapping[str, object]) -> list[list[Any]]:
        terms = str(values["query"]).lower().split()
        record_type = "chunk" if "TextChunk" in query else "node"
        rows = []
        for row in self._search_records(query, values):
            text = str(row.get("embedding_text") or row.get("text") or row.get("label") or "")
            score = float(sum(term in text.lower() for term in terms))
            if score:
                rows.append(
                    [row["id"], row["source_id"], text, row.get("source_location", ""), score, record_type]
                )
        return sorted(rows, key=lambda value: (-value[4], value[0]))[: int(values["limit"])]

    def _vector(self, query: str, values: Mapping[str, object]) -> list[list[Any]]:
        target = list(values["embedding"])
        target_norm = math.sqrt(sum(value * value for value in target)) or 1.0
        record_type = "chunk" if "TextChunk" in query else "node"
        rows = []
        for row in self._search_records(query, values):
            vector = row.get("embedding")
            if not vector:
                continue
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = sum(left * right for left, right in zip(vector, target)) / (norm * target_norm)
            text = str(row.get("embedding_text") or row.get("text") or row.get("label") or "")
            rows.append(
                [row["id"], row["source_id"], text, row.get("source_location", ""), score, record_type]
            )
        return sorted(rows, key=lambda value: (-value[4], value[0]))[: int(values["limit"])]

    def _store(
        self, records: dict[str, dict[str, Any]], values: Mapping[str, object], *, active: bool
    ) -> None:
        for raw in values.get("rows", []):
            row = dict(raw)
            row["workspace_id"] = values["workspace_id"]
            row["ingestion_version"] = values.get("version", "")
            row["active"] = active
            records[self._key(row, values)] = row

    def _publish(self, values: Mapping[str, object]) -> None:
        source_id = str(values["source_id"])
        version = str(values["version"])
        for records in (self.nodes, self.relationships, self.chunks, self.citations):
            for key, row in list(records.items()):
                if row.get("source_id") != source_id:
                    continue
                if row.get("ingestion_version") == version:
                    row["active"] = True
                else:
                    del records[key]
        self.manifests[source_id] = {
            "source_id": source_id,
            "active_version": version,
            "content_hash": values["content_hash"],
            "extractor_version": values["extractor_version"],
            "stage_status": "published",
        }

    @staticmethod
    def _delete_owned(
        records: dict[str, dict[str, Any]], values: Mapping[str, object], query: str
    ) -> None:
        for key, row in list(records.items()):
            if row.get("workspace_id") != values["workspace_id"]:
                continue
            if row.get("source_id") != values["source_id"]:
                continue
            if "version" in values and row.get("ingestion_version") != values["version"]:
                continue
            if "coalesce" in query and row.get("active", False):
                continue
            if "active_version" in values and row.get("ingestion_version") == values["active_version"]:
                continue
            del records[key]

    def ro_query(self, query: str, params: Mapping[str, object] | None = None, timeout=None):
        values = dict(params or {})
        if "MATCH (m:SourceManifest" in query:
            manifest = self.manifests.get(str(values["source_id"]))
            if manifest is None:
                return FakeResult([])
            return FakeResult(
                [[manifest["active_version"], manifest["content_hash"], manifest["extractor_version"]]]
            )
        if "MATCH (m:IndexManifest" in query:
            if self.index_manifest is None:
                return FakeResult([])
            return FakeResult(
                [[self.index_manifest["index_version"], self.index_manifest["dimension"]]]
            )
        if "count(record)" in query:
            if ":KnowledgeNode" in query:
                records = self.nodes
            elif ":RELATED" in query:
                records = self.relationships
            elif ":TextChunk" in query:
                records = self.chunks
            else:
                records = self.citations
            return FakeResult([[len(self._matches(records, values, active_only=False))]])
        if "collect(n.source_identity)" in query:
            matches = self._matches(self.nodes, values, active_only=True)
            return FakeResult([[sorted(row["source_identity"] for row in matches)]])
        if "count(n)" in query and "collect(DISTINCT n.source_id)" in query:
            matches = self._matches(self.nodes, values, active_only=True)
            return FakeResult([[len(matches), sorted({row["source_id"] for row in matches})]])
        if "count(DISTINCT n)" in query and "count(DISTINCT r)" in query:
            nodes = self._matches(self.nodes, values, active_only=True)
            relationships = self._matches(self.relationships, values, active_only=True)
            return FakeResult(
                [[len(nodes), len(relationships), sorted({row["source_id"] for row in nodes})]]
            )
        if "RETURN n.source_identity, n.label, n.node_type, n.source_id, n.text" in query:
            source_ids = set(values.get("source_ids", []))
            nodes = self._matches(self.nodes, values, active_only=True)
            if source_ids:
                nodes = [row for row in nodes if row["source_id"] in source_ids]
            nodes.sort(key=lambda row: (row["source_id"], row["source_identity"]))
            return FakeResult(
                [
                    [row["source_identity"], row["label"], row["node_type"], row["source_id"], row["text"]]
                    for row in nodes[: int(values["limit"])]
                ]
            )
        raise RuntimeError(f"fake does not implement read query: {query}")

    @staticmethod
    def _matches(
        records: Mapping[str, dict[str, Any]], values: Mapping[str, object], *, active_only: bool
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in records.values()
            if row.get("workspace_id") == values["workspace_id"]
            and ("source_id" not in values or row.get("source_id") == values["source_id"])
            and ("version" not in values or row.get("ingestion_version") == values["version"])
            and (not active_only or row.get("active", True))
        ]

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
