"""Scoped FalkorDB boundary with lazy optional dependency loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.contracts import GraphEnvelope
from kb_core_ui.rag.reconciler import SourceManifest, StageCounts
from kb_core_ui.rag.workspaces import workspace_graph_name

_WRITE_CLAUSES = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|FOREACH|LOAD\s+CSV)\b",
    re.IGNORECASE,
)
_CALL_CLAUSE = re.compile(r"\bCALL\b", re.IGNORECASE)
_WORKSPACE_PARAMETER = re.compile(r"\$workspace_id\b")
_LINE_COMMENT = re.compile(r"//[^\r\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


class AdapterError(RuntimeError):
    pass


class UnsafeCypherError(AdapterError):
    pass


class GraphHandle(Protocol):
    def query(
        self, query: str, params: Mapping[str, object] | None = None, timeout: int | None = None
    ) -> Any: ...

    def ro_query(
        self, query: str, params: Mapping[str, object] | None = None, timeout: int | None = None
    ) -> Any: ...

    def delete(self) -> None: ...


class Driver(Protocol):
    def ping(self) -> bool: ...

    def list_graphs(self) -> Sequence[str]: ...

    def select_graph(self, graph_name: str) -> GraphHandle: ...

    def close(self) -> None: ...


class FalkorDBDriver:
    """Small wrapper around official `FalkorDB` client."""

    def __init__(self, client: Any):
        self.client = client

    @classmethod
    def from_config(cls, config: RagConfig) -> "FalkorDBDriver":
        errors = config.readiness_errors()
        if errors:
            raise AdapterError("GraphRAG configuration is not ready: " + "; ".join(errors))
        try:
            from falkordb import FalkorDB
        except ImportError:
            raise AdapterError(
                "FalkorDB client is not installed; install kb-core-ui[rag]"
            ) from None
        kwargs: dict[str, object] = {
            "socket_timeout": config.query_timeout_seconds,
            "socket_connect_timeout": config.query_timeout_seconds,
        }
        if config.username:
            kwargs["username"] = config.username
        if config.password:
            kwargs["password"] = config.password
        if config.ssl:
            kwargs["ssl"] = True
        return cls(FalkorDB.from_url(config.falkordb_url, **kwargs))

    def ping(self) -> bool:
        return bool(self.client.connection.ping())

    def list_graphs(self) -> Sequence[str]:
        return self.client.list_graphs()

    def select_graph(self, graph_name: str) -> GraphHandle:
        return self.client.select_graph(graph_name)

    def close(self) -> None:
        self.client.close()


@dataclass(frozen=True)
class AdapterHealth:
    connected: bool
    graph_exists: bool
    graph_name: str
    error: str = ""


def _cypher_without_literals(query: str) -> str:
    value = _BLOCK_COMMENT.sub(" ", query)
    value = _LINE_COMMENT.sub(" ", value)
    return _STRING_LITERAL.sub("''", value)


def validate_read_only_cypher(query: str) -> None:
    if not query.strip():
        raise UnsafeCypherError("read query is empty")
    stripped = _cypher_without_literals(query)
    if ";" in stripped:
        raise UnsafeCypherError("multiple Cypher statements are not allowed")
    match = _WRITE_CLAUSES.search(stripped)
    if match:
        raise UnsafeCypherError(f"write clause {match.group(1).upper()} is not allowed")
    if _CALL_CLAUSE.search(stripped):
        raise UnsafeCypherError("CALL is not allowed in generated read queries")
    if not _WORKSPACE_PARAMETER.search(stripped):
        raise UnsafeCypherError("read query must scope records with $workspace_id")


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) or exc.__class__.__name__ in {
        "BusyLoadingError",
        "ConnectionError",
        "TimeoutError",
        "TryAgainError",
    }


def _rows(result: Any) -> list[Any]:
    value = getattr(result, "result_set", result)
    return list(value or [])


class FalkorDBAdapter:
    def __init__(
        self,
        config: RagConfig,
        workspace_id: str,
        *,
        driver: Driver | None = None,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ):
        errors = config.readiness_errors()
        if errors:
            raise AdapterError("GraphRAG configuration is not ready: " + "; ".join(errors))
        if retries < 0:
            raise ValueError("retries must be zero or greater")
        self.config = config
        self.workspace_id = workspace_id
        self.graph_name = workspace_graph_name(workspace_id)
        self.driver = driver or FalkorDBDriver.from_config(config)
        self.graph = self.driver.select_graph(self.graph_name)
        self.retries = retries
        self.sleep = sleep
        self.timeout_ms = config.query_timeout_seconds * 1_000

    def _run(self, operation: Callable[[], Any]) -> Any:
        for attempt in range(self.retries + 1):
            try:
                return operation()
            except Exception as exc:
                if attempt >= self.retries or not _is_transient(exc):
                    raise AdapterError(str(exc)) from exc
                self.sleep(0.05 * (2**attempt))
        raise AssertionError("retry loop must return or raise")

    def health(self) -> AdapterHealth:
        try:
            connected = bool(self._run(self.driver.ping))
            graph_exists = self.graph_name in self._run(self.driver.list_graphs)
            return AdapterHealth(connected, graph_exists, self.graph_name)
        except AdapterError as exc:
            return AdapterHealth(False, False, self.graph_name, str(exc))

    def ensure_graph(self) -> None:
        query = (
            "MERGE (m:WorkspaceMeta {workspace_id: $workspace_id}) "
            "SET m.graph_name = $graph_name, m.schema_version = $schema_version"
        )
        params = {
            "workspace_id": self.workspace_id,
            "graph_name": self.graph_name,
            "schema_version": "kb-core.rag.v1",
        }
        self._write(query, params)

    def delete_graph(self) -> None:
        self._run(self.graph.delete)

    def upsert_envelope(self, envelope: GraphEnvelope) -> None:
        if envelope.workspace_id != self.workspace_id:
            raise AdapterError(
                f"envelope workspace {envelope.workspace_id!r} does not match adapter workspace {self.workspace_id!r}"
            )
        self._upsert_active_envelope(envelope)

    def get_source_manifest(self, source_id: str) -> SourceManifest | None:
        if self.graph_name not in self._run(self.driver.list_graphs):
            return None
        rows = self.read_query(
            "MATCH (m:SourceManifest {workspace_id: $workspace_id, source_id: $source_id}) "
            "RETURN m.active_version, m.content_hash, m.extractor_version",
            {"source_id": source_id},
        )
        if not rows:
            return None
        return SourceManifest(source_id, str(rows[0][0]), str(rows[0][1]), str(rows[0][2]))

    def begin_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None:
        self.ensure_graph()
        self._write(
            "MERGE (m:SourceManifest {workspace_id: $workspace_id, source_id: $source_id}) "
            "SET m.staging_version = $version, m.staging_content_hash = $content_hash, "
            "m.staging_extractor_version = $extractor_version, m.stage_status = 'writing'",
            {
                "workspace_id": self.workspace_id,
                "source_id": source_id,
                "version": version,
                "content_hash": content_hash,
                "extractor_version": extractor_version,
            },
        )

    def stage_envelope(self, envelope: GraphEnvelope, version: str) -> None:
        if envelope.workspace_id != self.workspace_id:
            raise AdapterError(
                f"envelope workspace {envelope.workspace_id!r} does not match adapter workspace {self.workspace_id!r}"
            )
        self.ensure_graph()
        common = {"workspace_id": self.workspace_id, "version": version}
        if envelope.nodes:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (n:KnowledgeNode {id: row.id, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "SET n.source_id = row.source_id, n.source_identity = row.source_identity, "
                "n.node_type = row.node_type, n.label = row.label, n.text = row.text, "
                "n.source_location = row.source_location, n.provenance = row.provenance, "
                "n.properties_json = row.properties_json, n.active = false",
                {
                    **common,
                    "rows": [
                        {
                            **node.to_json_dict(),
                            "properties_json": json.dumps(
                                node.properties, sort_keys=True, ensure_ascii=False
                            ),
                        }
                        for node in envelope.nodes
                    ],
                },
            )
        if envelope.relationships:
            self._write(
                "UNWIND $rows AS row "
                "MATCH (a:KnowledgeNode {id: row.source, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "MATCH (b:KnowledgeNode {id: row.target, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "MERGE (a)-[r:RELATED {id: row.id, workspace_id: $workspace_id, "
                "ingestion_version: $version}]->(b) "
                "SET r.source_id = row.source_id, r.relationship_type = row.relationship_type, "
                "r.provenance = row.provenance, r.source_location = row.source_location, "
                "r.properties_json = row.properties_json, r.active = false",
                {
                    **common,
                    "rows": [
                        {
                            **edge.to_json_dict(),
                            "properties_json": json.dumps(
                                edge.properties, sort_keys=True, ensure_ascii=False
                            ),
                        }
                        for edge in envelope.relationships
                    ],
                },
            )
        if envelope.chunks:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (c:TextChunk {id: row.id, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "SET c.source_id = row.source_id, c.text = row.text, "
                "c.source_location = row.source_location, c.provenance = row.provenance, "
                "c.node_ids = row.node_ids, c.active = false",
                {**common, "rows": [chunk.to_json_dict() for chunk in envelope.chunks]},
            )
        if envelope.citations:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (c:Citation {id: row.id, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "SET c.source_id = row.source_id, c.chunk_id = row.chunk_id, c.title = row.title, "
                "c.source_location = row.source_location, c.source_uri = row.source_uri, "
                "c.active = false",
                {**common, "rows": [citation.to_json_dict() for citation in envelope.citations]},
            )

    def verify_source_stage(self, source_id: str, version: str) -> StageCounts:
        params = {"source_id": source_id, "version": version}

        def count(pattern: str) -> int:
            rows = self.read_query(f"MATCH {pattern} RETURN count(record)", params)
            return int(rows[0][0])

        return StageCounts(
            nodes=count(
                "(record:KnowledgeNode {workspace_id: $workspace_id, source_id: $source_id, "
                "ingestion_version: $version})"
            ),
            relationships=count(
                "()-[record:RELATED {workspace_id: $workspace_id, source_id: $source_id, "
                "ingestion_version: $version}]->()"
            ),
            chunks=count(
                "(record:TextChunk {workspace_id: $workspace_id, source_id: $source_id, "
                "ingestion_version: $version})"
            ),
            citations=count(
                "(record:Citation {workspace_id: $workspace_id, source_id: $source_id, "
                "ingestion_version: $version})"
            ),
        )

    def publish_source_stage(
        self, source_id: str, version: str, content_hash: str, extractor_version: str
    ) -> None:
        self._write(
            "MATCH (m:SourceManifest {workspace_id: $workspace_id, source_id: $source_id}) "
            "WHERE m.staging_version = $version "
            "OPTIONAL MATCH (newNode {workspace_id: $workspace_id, source_id: $source_id, "
            "ingestion_version: $version}) "
            "WHERE newNode:KnowledgeNode OR newNode:TextChunk OR newNode:Citation "
            "WITH m, collect(newNode) AS newNodes "
            "OPTIONAL MATCH ()-[newRel:RELATED {workspace_id: $workspace_id, "
            "source_id: $source_id, ingestion_version: $version}]-() "
            "WITH m, newNodes, collect(newRel) AS newRels "
            "FOREACH (n IN newNodes | SET n.active = true) "
            "FOREACH (r IN newRels | SET r.active = true) "
            "SET m.active_version = $version, m.content_hash = $content_hash, "
            "m.extractor_version = $extractor_version, m.stage_status = 'published', "
            "m.staging_version = null, m.staging_content_hash = null, "
            "m.staging_extractor_version = null "
            "WITH m "
            "OPTIONAL MATCH ()-[oldRel:RELATED {workspace_id: $workspace_id, "
            "source_id: $source_id}]-() "
            "WHERE coalesce(oldRel.ingestion_version, '') <> $version "
            "WITH m, [r IN collect(oldRel) WHERE r IS NOT NULL] AS oldRels "
            "FOREACH (r IN oldRels | DELETE r) "
            "WITH m "
            "OPTIONAL MATCH (oldNode {workspace_id: $workspace_id, source_id: $source_id}) "
            "WHERE (oldNode:KnowledgeNode OR oldNode:TextChunk OR oldNode:Citation) "
            "AND coalesce(oldNode.ingestion_version, '') <> $version "
            "WITH m, [n IN collect(oldNode) WHERE n IS NOT NULL] AS oldNodes "
            "FOREACH (n IN oldNodes | DETACH DELETE n) "
            "RETURN m.active_version",
            {
                "workspace_id": self.workspace_id,
                "source_id": source_id,
                "version": version,
                "content_hash": content_hash,
                "extractor_version": extractor_version,
            },
        )

    def recover_source(self, source_id: str, active_version: str) -> None:
        params = {
            "workspace_id": self.workspace_id,
            "source_id": source_id,
            "active_version": active_version,
        }
        self._write(
            "MATCH ()-[r:RELATED {workspace_id: $workspace_id, source_id: $source_id}]-() "
            "WHERE coalesce(r.active, false) = false "
            "AND coalesce(r.ingestion_version, '') <> $active_version DELETE r",
            params,
        )
        self._write(
            "MATCH (n {workspace_id: $workspace_id, source_id: $source_id}) "
            "WHERE (n:KnowledgeNode OR n:TextChunk OR n:Citation) "
            "AND coalesce(n.active, false) = false "
            "AND coalesce(n.ingestion_version, '') <> $active_version DETACH DELETE n",
            params,
        )
        self._write(
            "MATCH (m:SourceManifest {workspace_id: $workspace_id, source_id: $source_id}) "
            "SET m.staging_version = null, m.staging_content_hash = null, "
            "m.staging_extractor_version = null, m.stage_status = 'recovered'",
            params,
        )

    def rollback_source_stage(self, source_id: str, version: str) -> None:
        params = {
            "workspace_id": self.workspace_id,
            "source_id": source_id,
            "version": version,
        }
        self._write(
            "MATCH ()-[r:RELATED {workspace_id: $workspace_id, source_id: $source_id, "
            "ingestion_version: $version}]-() WHERE coalesce(r.active, false) = false DELETE r",
            params,
        )
        self._write(
            "MATCH (n {workspace_id: $workspace_id, source_id: $source_id, "
            "ingestion_version: $version}) "
            "WHERE (n:KnowledgeNode OR n:TextChunk OR n:Citation) "
            "AND coalesce(n.active, false) = false DETACH DELETE n",
            params,
        )
        self._write(
            "MATCH (m:SourceManifest {workspace_id: $workspace_id, source_id: $source_id}) "
            "WHERE m.staging_version = $version "
            "SET m.staging_version = null, m.staging_content_hash = null, "
            "m.staging_extractor_version = null, m.stage_status = 'rolled_back'",
            params,
        )

    def _upsert_active_envelope(self, envelope: GraphEnvelope) -> None:
        self.ensure_graph()
        if envelope.nodes:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (n:KnowledgeNode {id: row.id, workspace_id: $workspace_id}) "
                "SET n.source_id = row.source_id, n.source_identity = row.source_identity, "
                "n.node_type = row.node_type, n.label = row.label, n.text = row.text, "
                "n.source_location = row.source_location, n.provenance = row.provenance, "
                "n.properties_json = row.properties_json",
                {
                    "workspace_id": self.workspace_id,
                    "rows": [
                        {
                            **node.to_json_dict(),
                            "properties_json": json.dumps(
                                node.properties, sort_keys=True, ensure_ascii=False
                            ),
                        }
                        for node in envelope.nodes
                    ],
                },
            )
        if envelope.relationships:
            self._write(
                "UNWIND $rows AS row "
                "MATCH (a:KnowledgeNode {id: row.source, workspace_id: $workspace_id}) "
                "MATCH (b:KnowledgeNode {id: row.target, workspace_id: $workspace_id}) "
                "MERGE (a)-[r:RELATED {id: row.id, workspace_id: $workspace_id}]->(b) "
                "SET r.source_id = row.source_id, r.relationship_type = row.relationship_type, "
                "r.provenance = row.provenance, r.source_location = row.source_location, "
                "r.properties_json = row.properties_json",
                {
                    "workspace_id": self.workspace_id,
                    "rows": [
                        {
                            **edge.to_json_dict(),
                            "properties_json": json.dumps(
                                edge.properties, sort_keys=True, ensure_ascii=False
                            ),
                        }
                        for edge in envelope.relationships
                    ],
                },
            )
        if envelope.chunks:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (c:TextChunk {id: row.id, workspace_id: $workspace_id}) "
                "SET c.source_id = row.source_id, c.text = row.text, "
                "c.source_location = row.source_location, c.provenance = row.provenance, "
                "c.node_ids = row.node_ids",
                {
                    "workspace_id": self.workspace_id,
                    "rows": [chunk.to_json_dict() for chunk in envelope.chunks],
                },
            )
        if envelope.citations:
            self._write(
                "UNWIND $rows AS row "
                "MERGE (c:Citation {id: row.id, workspace_id: $workspace_id}) "
                "SET c.source_id = row.source_id, c.chunk_id = row.chunk_id, c.title = row.title, "
                "c.source_location = row.source_location, c.source_uri = row.source_uri",
                {
                    "workspace_id": self.workspace_id,
                    "rows": [citation.to_json_dict() for citation in envelope.citations],
                },
            )

    def delete_source(self, source_id: str) -> None:
        if not source_id:
            raise AdapterError("source id is required")
        params = {"workspace_id": self.workspace_id, "source_id": source_id}
        self._write(
            "MATCH ()-[r:RELATED {workspace_id: $workspace_id, source_id: $source_id}]-() DELETE r",
            params,
        )
        self._write(
            "MATCH (n {workspace_id: $workspace_id, source_id: $source_id}) DETACH DELETE n",
            params,
        )

    def read_query(self, query: str, params: Mapping[str, object] | None = None) -> list[Any]:
        validate_read_only_cypher(query)
        scoped_params = dict(params or {})
        requested_workspace = scoped_params.get("workspace_id")
        if requested_workspace not in {None, self.workspace_id}:
            raise AdapterError("workspace_id parameter does not match adapter workspace")
        scoped_params["workspace_id"] = self.workspace_id
        result = self._run(
            lambda: self.graph.ro_query(query, params=scoped_params, timeout=self.timeout_ms)
        )
        return _rows(result)

    def _write(self, query: str, params: Mapping[str, object]) -> list[Any]:
        if "$workspace_id" not in query:
            raise AdapterError("write query must scope records with $workspace_id")
        scoped_params = dict(params)
        scoped_params["workspace_id"] = self.workspace_id
        result = self._run(
            lambda: self.graph.query(query, params=scoped_params, timeout=self.timeout_ms)
        )
        return _rows(result)

    def close(self) -> None:
        self.driver.close()
