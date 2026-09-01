"""Scoped FalkorDB boundary with lazy optional dependency loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.contracts import GraphEnvelope
from kb_core_ui.rag.indexing import SearchCandidate
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
_WRITE_BATCH_SIZE = 500


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

    def _write_rows(self, query: str, params: Mapping[str, object]) -> None:
        rows = params.get("rows")
        if not isinstance(rows, Sequence):
            raise AdapterError("batched write requires a rows sequence")
        common = {key: value for key, value in params.items() if key != "rows"}
        for start in range(0, len(rows), _WRITE_BATCH_SIZE):
            self._write(query, {**common, "rows": rows[start : start + _WRITE_BATCH_SIZE]})

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

    def _ensure_ingestion_indexes(self) -> None:
        rows = self._admin_query(
            "CALL db.indexes() YIELD label, properties RETURN label, properties",
            {},
        )
        if any(str(label) == "KnowledgeNode" and "id" in properties for label, properties in rows):
            return
        self._admin_query("CREATE INDEX FOR (n:KnowledgeNode) ON (n.id)", {})

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
        self._ensure_ingestion_indexes()
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
            self._write_rows(
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
            self._write_rows(
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
            self._write_rows(
                "UNWIND $rows AS row "
                "MERGE (c:TextChunk {id: row.id, workspace_id: $workspace_id, "
                "ingestion_version: $version}) "
                "SET c.source_id = row.source_id, c.text = row.text, "
                "c.source_location = row.source_location, c.provenance = row.provenance, "
                "c.node_ids = row.node_ids, c.active = false",
                {**common, "rows": [chunk.to_json_dict() for chunk in envelope.chunks]},
            )
        if envelope.citations:
            self._write_rows(
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

    def write_embeddings(
        self,
        envelope: GraphEnvelope,
        version: str,
        chunk_rows: Sequence[dict[str, Any]],
        node_rows: Sequence[dict[str, Any]],
    ) -> None:
        if envelope.workspace_id != self.workspace_id:
            raise AdapterError("embedding envelope does not match adapter workspace")
        common = {
            "workspace_id": self.workspace_id,
            "source_id": envelope.source_id,
            "version": version,
        }
        if chunk_rows:
            self._write_rows(
                "UNWIND $rows AS row "
                "MATCH (c:TextChunk {id: row.id, workspace_id: $workspace_id, "
                "source_id: $source_id, ingestion_version: $version}) "
                "SET c.embedding = vecf32(row.embedding)",
                {**common, "rows": list(chunk_rows)},
            )
        if node_rows:
            self._write_rows(
                "UNWIND $rows AS row "
                "MATCH (n:KnowledgeNode {id: row.id, workspace_id: $workspace_id, "
                "source_id: $source_id, ingestion_version: $version}) "
                "SET n.embedding = vecf32(row.embedding), n.embedding_text = row.embedding_text",
                {**common, "rows": list(node_rows)},
            )

    def ensure_retrieval_indexes(self, dimension: int, index_version: str) -> int:
        if not 1 <= dimension <= 4_096:
            raise AdapterError("vector index dimension must be between 1 and 4096")
        manifests = self.read_query(
            "MATCH (m:IndexManifest {workspace_id: $workspace_id}) "
            "RETURN m.index_version, m.dimension"
        )
        current = (str(manifests[0][0]), int(manifests[0][1])) if manifests else None
        if current != (index_version, dimension):
            if current is not None:
                self._admin_query(
                    "DROP INDEX FOR (n:TextChunk) ON (n.embedding)",
                    {"workspace_id": self.workspace_id},
                )
                self._admin_query(
                    "DROP INDEX FOR (n:KnowledgeNode) ON (n.embedding)",
                    {"workspace_id": self.workspace_id},
                )
            if current is None:
                self._admin_query(
                    "CREATE FULLTEXT INDEX FOR (n:TextChunk) ON (n.text)",
                    {"workspace_id": self.workspace_id},
                )
                self._admin_query(
                    "CREATE FULLTEXT INDEX FOR (n:KnowledgeNode) ON (n.label, n.text)",
                    {"workspace_id": self.workspace_id},
                )
            self._admin_query(
                "CREATE VECTOR INDEX FOR (n:TextChunk) ON (n.embedding) "
                f"OPTIONS {{dimension: {dimension}, similarityFunction: 'cosine'}}",
                {"workspace_id": self.workspace_id},
            )
            self._admin_query(
                "CREATE VECTOR INDEX FOR (n:KnowledgeNode) ON (n.embedding) "
                f"OPTIONS {{dimension: {dimension}, similarityFunction: 'cosine'}}",
                {"workspace_id": self.workspace_id},
            )
            self._write(
                "MERGE (m:IndexManifest {workspace_id: $workspace_id}) "
                "SET m.index_version = $index_version, m.dimension = $dimension",
                {
                    "workspace_id": self.workspace_id,
                    "index_version": index_version,
                    "dimension": dimension,
                },
            )
        required = {
            "TextChunk": {"text": "FULLTEXT", "embedding": "VECTOR"},
            "KnowledgeNode": {
                "label": "FULLTEXT",
                "text": "FULLTEXT",
                "embedding": "VECTOR",
            },
        }
        deadline = time.monotonic() + self.config.query_timeout_seconds
        while True:
            rows = self._admin_query(
                "CALL db.indexes() YIELD label, properties, types, status "
                "WHERE label IN ['TextChunk', 'KnowledgeNode'] "
                "RETURN label, properties, types, status",
                {"workspace_id": self.workspace_id},
            )
            actual: dict[str, dict[str, set[str]]] = {}
            for label, properties, types, status in rows:
                if str(status).upper() != "OPERATIONAL":
                    continue
                label_types = actual.setdefault(str(label), {})
                if isinstance(types, Mapping):
                    for prop, values in types.items():
                        label_types.setdefault(str(prop), set()).update(map(str, values))
                else:
                    for prop, values in zip(properties, types):
                        nested = values if isinstance(values, (list, tuple, set)) else [values]
                        label_types.setdefault(str(prop), set()).update(map(str, nested))
            missing = [
                f"{label}.{prop}:{kind}"
                for label, properties in required.items()
                for prop, kind in properties.items()
                if kind not in actual.get(label, {}).get(prop, set())
            ]
            if not missing:
                return 4
            if time.monotonic() >= deadline:
                raise AdapterError("retrieval indexes incomplete: " + ", ".join(missing))
            self.sleep(0.25)

    def fulltext_search(
        self, query: str, limit: int, source_ids: Sequence[str]
    ) -> list[SearchCandidate]:
        if not query.strip():
            return []
        values = {
            "workspace_id": self.workspace_id,
            "source_ids": list(source_ids),
            "query": query,
            "limit": limit,
        }
        candidates = self._search_candidates(
            "CALL db.idx.fulltext.queryNodes('TextChunk', $query) YIELD node, score ",
            "node.text",
            "chunk",
            values,
        )
        candidates += self._search_candidates(
            "CALL db.idx.fulltext.queryNodes('KnowledgeNode', $query) YIELD node, score ",
            "coalesce(node.embedding_text, node.text, node.label)",
            "node",
            values,
        )
        return sorted(candidates, key=lambda item: (-item.score, item.id))[:limit]

    def vector_search(
        self, embedding: Sequence[float], limit: int, source_ids: Sequence[str]
    ) -> list[SearchCandidate]:
        values = {
            "workspace_id": self.workspace_id,
            "source_ids": list(source_ids),
            "embedding": list(map(float, embedding)),
            "limit": limit,
        }
        candidates = self._search_candidates(
            "CALL db.idx.vector.queryNodes('TextChunk', 'embedding', $limit, "
            "vecf32($embedding)) YIELD node, score ",
            "node.text",
            "chunk",
            values,
        )
        candidates += self._search_candidates(
            "CALL db.idx.vector.queryNodes('KnowledgeNode', 'embedding', $limit, "
            "vecf32($embedding)) YIELD node, score ",
            "coalesce(node.embedding_text, node.text, node.label)",
            "node",
            values,
        )
        return sorted(candidates, key=lambda item: (-item.score, item.id))[:limit]

    def _search_candidates(
        self,
        procedure: str,
        text_expression: str,
        record_type: str,
        params: Mapping[str, object],
    ) -> list[SearchCandidate]:
        query = (
            procedure
            + "WHERE node.workspace_id = $workspace_id AND coalesce(node.active, true) = true "
            "AND (size($source_ids) = 0 OR node.source_id IN $source_ids) "
            f"RETURN node.id, node.source_id, {text_expression}, "
            f"node.source_location, score, '{record_type}' LIMIT $limit"
        )
        rows = self._admin_query(query, params)
        return [
            SearchCandidate(
                id=str(row[0]),
                source_id=str(row[1]),
                text=str(row[2] or ""),
                source_location=str(row[3] or ""),
                score=float(row[4]),
                record_type=str(row[5]),
            )
            for row in rows
        ]

    def _admin_query(self, query: str, params: Mapping[str, object]) -> list[Any]:
        scoped = dict(params)
        scoped["workspace_id"] = self.workspace_id
        result = self._run(
            lambda: self.graph.query(query, params=scoped, timeout=self.timeout_ms)
        )
        return _rows(result)

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

    # -- Chat thread/turn persistence (T10) ---------------------------------
    #
    # Reuses this adapter's own write/read primitives; never opens a second
    # database client. Every record also carries an explicit workspace_id
    # property (C3 defense-in-depth) in addition to already living inside
    # this workspace's own FalkorDB graph.

    def write_chat_turn(
        self,
        thread_key: str,
        thread_id: str,
        turn_id: str,
        query_text: str,
        response_json: str,
        created_at: str,
    ) -> int:
        """Atomically create the thread record (on first use) and append one
        complete turn in a single write. Returns the turn's 1-based sequence
        number within the thread."""

        rows = self._write(
            "MERGE (t:ChatThread {id: $thread_key, workspace_id: $workspace_id}) "
            "ON CREATE SET t.thread_id = $thread_id, t.created_at = $created_at, "
            "t.next_seq = 0 "
            "SET t.next_seq = t.next_seq + 1, t.updated_at = $created_at "
            "WITH t "
            "CREATE (c:ChatTurn {id: $turn_id, thread_key: $thread_key, "
            "workspace_id: $workspace_id, seq: t.next_seq, query: $query_text, "
            "response_json: $response_json, created_at: $created_at}) "
            "RETURN t.next_seq",
            {
                "thread_key": thread_key,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "query_text": query_text,
                "response_json": response_json,
                "created_at": created_at,
            },
        )
        return int(rows[0][0])

    def list_chat_turns(self, thread_key: str) -> list[Any]:
        return self.read_query(
            "MATCH (c:ChatTurn {thread_key: $thread_key, workspace_id: $workspace_id}) "
            "RETURN c.id, c.seq, c.query, c.response_json, c.created_at",
            {"thread_key": thread_key},
        )

    def trim_chat_turns(self, thread_key: str, cutoff_seq: int) -> None:
        """Delete turns at or below ``cutoff_seq`` for one thread (retention)."""

        self._write(
            "MATCH (c:ChatTurn {thread_key: $thread_key, workspace_id: $workspace_id}) "
            "WHERE c.seq <= $cutoff_seq DETACH DELETE c",
            {"thread_key": thread_key, "cutoff_seq": cutoff_seq},
        )

    def delete_chat_thread(self, thread_key: str) -> None:
        self._write(
            "MATCH (c:ChatTurn {thread_key: $thread_key, workspace_id: $workspace_id}) "
            "DETACH DELETE c",
            {"thread_key": thread_key},
        )
        self._write(
            "MATCH (t:ChatThread {id: $thread_key, workspace_id: $workspace_id}) "
            "DETACH DELETE t",
            {"thread_key": thread_key},
        )

    def delete_all_chat_threads(self) -> int:
        """Delete every thread/turn owned by this adapter's workspace only.
        Because each adapter is bound to exactly one FalkorDB graph (C3), this
        can never reach another workspace's records."""

        rows = self.read_query(
            "MATCH (t:ChatThread {workspace_id: $workspace_id}) RETURN count(t)"
        )
        count = int(rows[0][0]) if rows else 0
        self._write(
            "MATCH (c:ChatTurn {workspace_id: $workspace_id}) DETACH DELETE c", {}
        )
        self._write(
            "MATCH (t:ChatThread {workspace_id: $workspace_id}) DETACH DELETE t", {}
        )
        return count

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
