"""LangGraph-backed RAG chat workflow: scope validation -> hybrid retrieval ->
entity expansion -> safe read-only graph query -> evidence ranking -> answer
synthesis -> citation validation.

This module never opens a second database client. The graph-query node is
built exclusively on top of ``FalkorDBAdapter.read_query`` (timeout-bounded,
workspace-scoped, and gated by ``validate_read_only_cypher``); the retrieval
node is built exclusively on top of ``HybridRetriever``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any, Callable, Mapping, Protocol, Sequence, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.falkordb_adapter import AdapterError, UnsafeCypherError, validate_read_only_cypher
from kb_core_ui.rag.indexing import EmbeddingProvider, HybridRetriever, IndexingError, RetrievalHit
from kb_core_ui.rag.workspaces import WorkspaceError, WorkspaceRegistry

INSUFFICIENT_EVIDENCE_TEXT = (
    "I don't have enough evidence in the retrieved sources to answer that question."
)
PROVIDER_UNAVAILABLE_TEXT = (
    "The assistant provider is temporarily unavailable after retrying; please try again."
)
CANCELLED_TEXT = "Query was cancelled before completion."


class WorkflowError(RuntimeError):
    pass


class ProviderError(RuntimeError):
    pass


class ProviderTransientError(ProviderError):
    """Raised by a chat model implementation for a retryable failure."""


# --------------------------------------------------------------------------- #
# Hard limits
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RetrievalLimits:
    """Bounded retrieval/traversal/result/token limits.

    Values are always the minimum of what the caller requested and what the
    server config allows -- a request can only ever narrow limits, never
    widen them past server config (V7: "no unbounded traversal").
    """

    hybrid_k: int
    graph_traversal_seeds: int
    graph_row_limit: int
    max_answer_tokens: int
    max_provider_retries: int

    @classmethod
    def resolve(
        cls,
        config: RagConfig,
        *,
        requested_k: int | None = None,
        requested_graph_row_limit: int | None = None,
    ) -> "RetrievalLimits":
        hybrid_k = config.max_hybrid_k
        if requested_k is not None and requested_k >= 1:
            hybrid_k = min(requested_k, config.max_hybrid_k)
        graph_row_limit = config.max_graph_row_limit
        if requested_graph_row_limit is not None and requested_graph_row_limit >= 1:
            graph_row_limit = min(requested_graph_row_limit, config.max_graph_row_limit)
        return cls(
            hybrid_k=hybrid_k,
            graph_traversal_seeds=config.max_graph_traversal_seeds,
            graph_row_limit=graph_row_limit,
            max_answer_tokens=config.max_answer_tokens,
            max_provider_retries=config.max_provider_retries,
        )


# --------------------------------------------------------------------------- #
# Strong, allowlist-based read-only Cypher validator for LLM-proposed queries
# --------------------------------------------------------------------------- #

_ALLOWED_CLAUSE_KEYWORDS = frozenset(
    {
        "MATCH",
        "OPTIONAL",
        "WHERE",
        "RETURN",
        "WITH",
        "ORDER",
        "BY",
        "LIMIT",
        "SKIP",
        "UNWIND",
        "AS",
        "DISTINCT",
        "AND",
        "OR",
        "NOT",
        "XOR",
        "IN",
        "IS",
        "NULL",
        "ASC",
        "DESC",
        "COALESCE",
        "COUNT",
        "TRUE",
        "FALSE",
    }
)
ALLOWED_LABELS_AND_RELATIONSHIPS = frozenset(
    {"KnowledgeNode", "TextChunk", "Citation", "RELATED"}
)
ALLOWED_PROPERTIES = frozenset(
    {
        "id",
        "workspace_id",
        "source_id",
        "source_identity",
        "node_type",
        "label",
        "text",
        "source_location",
        "provenance",
        "properties_json",
        "chunk_id",
        "title",
        "source_uri",
        "node_ids",
        "active",
        "ingestion_version",
    }
)
ALLOWED_PARAMETERS = frozenset({"workspace_id", "source_ids", "seed_ids", "query", "limit", "embedding"})

_LINE_COMMENT = re.compile(r"//[^\r\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
_LABEL_OR_REL_TOKEN = re.compile(r":\s*([A-Za-z_][A-Za-z0-9_]*)")
_PROPERTY_TOKEN = re.compile(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)")
_PARAMETER_TOKEN = re.compile(r"\$\s*([A-Za-z_][A-Za-z0-9_]*)")
_UPPER_WORD_TOKEN = re.compile(r"\b[A-Z][A-Z_]{2,}\b")


def _strip_literals(query: str) -> str:
    value = _BLOCK_COMMENT.sub(" ", query)
    value = _LINE_COMMENT.sub(" ", value)
    return _STRING_LITERAL.sub("''", value)


def validate_generated_cypher(query: str) -> None:
    """Reject any generated Cypher that is not a bounded, read-only, scoped,
    schema-constrained query built only from allowlisted clauses, labels,
    relationship types, properties, and parameters.

    Timeout bounding is enforced structurally by construction: the
    graph-query node only ever executes an accepted query through
    ``FalkorDBAdapter.read_query``, which always applies the adapter's
    configured query timeout. This validator never patches a rejected
    query -- callers must reject and take the safe fallback branch.
    """

    # Baseline: no writes, no CALL, single statement, workspace predicate present.
    validate_read_only_cypher(query)

    stripped = _strip_literals(query)

    if "LIMIT $limit" not in stripped:
        raise UnsafeCypherError(
            "generated query must bound its result rows with a parameterized LIMIT $limit"
        )

    labels = set(_LABEL_OR_REL_TOKEN.findall(stripped))
    disallowed_labels = labels - ALLOWED_LABELS_AND_RELATIONSHIPS
    if disallowed_labels:
        raise UnsafeCypherError(
            f"disallowed label or relationship type: {sorted(disallowed_labels)}"
        )

    properties = set(_PROPERTY_TOKEN.findall(stripped))
    disallowed_properties = properties - ALLOWED_PROPERTIES
    if disallowed_properties:
        raise UnsafeCypherError(f"disallowed property reference: {sorted(disallowed_properties)}")

    parameters = set(_PARAMETER_TOKEN.findall(stripped))
    disallowed_parameters = parameters - ALLOWED_PARAMETERS
    if disallowed_parameters:
        raise UnsafeCypherError(f"disallowed parameter reference: {sorted(disallowed_parameters)}")

    keywords = set(_UPPER_WORD_TOKEN.findall(stripped))
    unknown_keywords = keywords - _ALLOWED_CLAUSE_KEYWORDS - ALLOWED_LABELS_AND_RELATIONSHIPS
    if unknown_keywords:
        raise UnsafeCypherError(f"disallowed keyword or clause: {sorted(unknown_keywords)}")


# --------------------------------------------------------------------------- #
# Evidence, citations, request/response contracts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    source_id: str
    text: str
    source_location: str
    score: float
    origin: str  # "retrieval" | "graph"

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "text": self.text,
            "source_location": self.source_location,
            "score": self.score,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class ChatAnswer:
    text: str
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatRequest:
    workspace_id: str
    query: str
    allowed_source_ids: Sequence[str] = ()
    strategy: str = "auto"
    query_id: str = ""
    requested_k: int | None = None
    requested_graph_row_limit: int | None = None
    cancelled: bool = False


@dataclass(frozen=True)
class ChatResponse:
    workspace_id: str
    query_id: str
    answer: str
    citations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    degraded: bool
    insufficient_evidence: bool
    strategy: str
    errors: list[str]
    timings: dict[str, float]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "query_id": self.query_id,
            "answer": self.answer,
            "citations": self.citations,
            "evidence": self.evidence,
            "degraded": self.degraded,
            "insufficient_evidence": self.insufficient_evidence,
            "strategy": self.strategy,
            "errors": self.errors,
            "timings": self.timings,
        }


# --------------------------------------------------------------------------- #
# Provider protocol and deterministic fake chat model
# --------------------------------------------------------------------------- #


class ChatModel(Protocol):
    def propose_expansion(
        self,
        query: str,
        workspace_id: str,
        seed_ids: Sequence[str],
        limit: int,
    ) -> str:
        """Return a Cypher string proposal (may be unsafe; validated by caller)."""
        ...

    def synthesize(self, query: str, evidence: Sequence[EvidenceItem]) -> ChatAnswer:
        """Return an answer with citations referencing evidence ids. May raise
        ``ProviderTransientError`` for a retryable failure."""
        ...


_DEFAULT_EXPANSION_TEMPLATE = (
    "MATCH (seed:KnowledgeNode {workspace_id: $workspace_id})-[:RELATED]-"
    "(m:KnowledgeNode {workspace_id: $workspace_id}) "
    "WHERE seed.id IN $seed_ids "
    "RETURN DISTINCT m.id, m.source_id, m.label, m.text, m.source_location "
    "LIMIT $limit"
)


class FakeChatModel:
    """Deterministic provider used by default tests and CI. Needs no API key."""

    def __init__(self, *, unsafe_expansion: bool = False, fail_times: int = 0):
        self.unsafe_expansion = unsafe_expansion
        self._fail_times = fail_times
        self._synthesize_calls = 0
        self.expansion_calls: list[tuple[str, tuple[str, ...]]] = []

    def propose_expansion(
        self, query: str, workspace_id: str, seed_ids: Sequence[str], limit: int
    ) -> str:
        self.expansion_calls.append((query, tuple(seed_ids)))
        if not seed_ids:
            return ""
        if self.unsafe_expansion:
            return "MATCH (n) DETACH DELETE n RETURN n"
        return _DEFAULT_EXPANSION_TEMPLATE

    def synthesize(self, query: str, evidence: Sequence[EvidenceItem]) -> ChatAnswer:
        self._synthesize_calls += 1
        if self._synthesize_calls <= self._fail_times:
            raise ProviderTransientError("simulated transient provider failure")
        if not evidence:
            return ChatAnswer(text=INSUFFICIENT_EVIDENCE_TEXT, citation_ids=())
        top = list(evidence[: min(3, len(evidence))])
        citation_ids = tuple(item.id for item in top)
        fragments = [item.text.strip()[:160] for item in top if item.text.strip()]
        if not fragments:
            return ChatAnswer(text=INSUFFICIENT_EVIDENCE_TEXT, citation_ids=())
        body = "; ".join(f"{fragment} [{item.id}]" for fragment, item in zip(fragments, top))
        return ChatAnswer(text=f"Based on the retrieved sources: {body}", citation_ids=citation_ids)


# --------------------------------------------------------------------------- #
# Adapter protocol used by the graph-query node (subset of FalkorDBAdapter)
# --------------------------------------------------------------------------- #


class GraphReadAdapter(Protocol):
    def read_query(self, query: str, params: Mapping[str, object] | None = None) -> list[Any]: ...


# --------------------------------------------------------------------------- #
# Typed workflow state
# --------------------------------------------------------------------------- #


class ChatWorkflowState(TypedDict, total=False):
    workspace_id: str
    allowed_source_ids: tuple[str, ...]
    query: str
    strategy: str
    limits: RetrievalLimits
    scope_valid: bool
    retrieval_hits: tuple[RetrievalHit, ...]
    expansion_seed_ids: tuple[str, ...]
    expansion_cypher: str
    graph_evidence: tuple[EvidenceItem, ...]
    evidence: tuple[EvidenceItem, ...]
    citation_ids: tuple[str, ...]
    citations: tuple[dict[str, Any], ...]
    answer: str
    degraded: bool
    insufficient_evidence: bool
    errors: tuple[str, ...]
    timings: dict[str, float]
    cancelled: bool


def _append(state: ChatWorkflowState, message: str) -> tuple[str, ...]:
    return (*state.get("errors", ()), message)


# --------------------------------------------------------------------------- #
# Workflow
# --------------------------------------------------------------------------- #


class ChatWorkflow:
    """Compiled LangGraph RAG chat workflow bound to one workspace's adapter."""

    def __init__(
        self,
        *,
        adapter: GraphReadAdapter,
        registry: WorkspaceRegistry,
        chat_model: ChatModel,
        embeddings: EmbeddingProvider,
        config: RagConfig,
        retriever: HybridRetriever | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.chat_model = chat_model
        self.config = config
        self.retriever = retriever or HybridRetriever(adapter, embeddings, max_k=config.max_hybrid_k)
        self.sleep = sleep
        self._graph = self._build_graph()

    # -- graph construction -------------------------------------------------

    def _build_graph(self):
        builder = StateGraph(ChatWorkflowState)
        builder.add_node("scope_validation", self._timed("scope_validation", self._scope_validation))
        builder.add_node("hybrid_retrieval", self._timed("hybrid_retrieval", self._hybrid_retrieval))
        builder.add_node("entity_expansion", self._timed("entity_expansion", self._entity_expansion))
        builder.add_node("graph_query", self._timed("graph_query", self._graph_query))
        builder.add_node("evidence_ranking", self._timed("evidence_ranking", self._evidence_ranking))
        builder.add_node("answer_synthesis", self._timed("answer_synthesis", self._answer_synthesis))
        builder.add_node(
            "citation_validation", self._timed("citation_validation", self._citation_validation)
        )

        builder.add_edge(START, "scope_validation")
        builder.add_conditional_edges(
            "scope_validation",
            self._route_after_scope,
            {"hybrid_retrieval": "hybrid_retrieval", "evidence_ranking": "evidence_ranking"},
        )
        builder.add_conditional_edges(
            "hybrid_retrieval",
            self._route_after_retrieval,
            {"entity_expansion": "entity_expansion", "evidence_ranking": "evidence_ranking"},
        )
        builder.add_edge("entity_expansion", "graph_query")
        builder.add_edge("graph_query", "evidence_ranking")
        builder.add_edge("evidence_ranking", "answer_synthesis")
        builder.add_edge("answer_synthesis", "citation_validation")
        builder.add_edge("citation_validation", END)
        return builder.compile()

    @staticmethod
    def _timed(
        name: str, fn: Callable[[ChatWorkflowState], dict[str, Any]]
    ) -> Callable[[ChatWorkflowState], dict[str, Any]]:
        def wrapper(state: ChatWorkflowState) -> dict[str, Any]:
            start = time.monotonic()
            result = dict(fn(state))
            timings = dict(state.get("timings", {}))
            timings[name] = round((time.monotonic() - start) * 1000, 3)
            result["timings"] = timings
            return result

        return wrapper

    # -- routing --------------------------------------------------------

    @staticmethod
    def _route_after_scope(state: ChatWorkflowState) -> str:
        if not state.get("scope_valid", True):
            return "evidence_ranking"
        return "hybrid_retrieval"

    @staticmethod
    def _route_after_retrieval(state: ChatWorkflowState) -> str:
        if state.get("retrieval_hits"):
            return "entity_expansion"
        return "evidence_ranking"

    # -- nodes ------------------------------------------------------------

    def _scope_validation(self, state: ChatWorkflowState) -> dict[str, Any]:
        errors = list(state.get("errors", ()))
        workspace_id = state["workspace_id"]
        try:
            workspace = self.registry.get(workspace_id)
        except WorkspaceError as exc:
            errors.append(f"invalid_workspace: {exc}")
            return {
                "allowed_source_ids": (),
                "errors": tuple(errors),
                "scope_valid": False,
                "insufficient_evidence": True,
            }

        requested = tuple(state.get("allowed_source_ids") or ())
        owned = set(workspace.sources)
        rejected = sorted(sid for sid in requested if sid not in owned)
        if rejected:
            errors.append(f"rejected_source_ids: {rejected}")
        effective = tuple(sorted(sid for sid in requested if sid in owned)) if requested else ()

        query_empty = not state.get("query", "").strip()
        if query_empty:
            errors.append("empty_query")

        cancelled = bool(state.get("cancelled"))
        if cancelled:
            errors.append("cancelled")

        return {
            "allowed_source_ids": effective,
            "errors": tuple(errors),
            "scope_valid": not query_empty and not cancelled,
            "insufficient_evidence": query_empty,
        }

    def _hybrid_retrieval(self, state: ChatWorkflowState) -> dict[str, Any]:
        limits: RetrievalLimits = state["limits"]
        try:
            hits = self.retriever.search(
                state["query"], k=limits.hybrid_k, source_ids=state.get("allowed_source_ids", ())
            )
        except AdapterError as exc:
            return {
                "retrieval_hits": (),
                "degraded": True,
                "errors": _append(state, f"retrieval_failed: {exc}"),
            }
        except IndexingError as exc:
            return {"retrieval_hits": (), "errors": _append(state, f"retrieval_error: {exc}")}
        return {"retrieval_hits": tuple(hits)}

    def _entity_expansion(self, state: ChatWorkflowState) -> dict[str, Any]:
        limits: RetrievalLimits = state["limits"]
        seeds = tuple(
            hit.id
            for hit in state.get("retrieval_hits", ())
            if hit.record_type == "node"
        )[: limits.graph_traversal_seeds]
        if not seeds:
            return {"expansion_cypher": "", "expansion_seed_ids": ()}
        cypher = self.chat_model.propose_expansion(
            state["query"], state["workspace_id"], seeds, limits.graph_row_limit
        )
        return {"expansion_cypher": cypher, "expansion_seed_ids": seeds}

    def _graph_query(self, state: ChatWorkflowState) -> dict[str, Any]:
        cypher = state.get("expansion_cypher") or ""
        if not cypher.strip():
            return {"graph_evidence": ()}

        try:
            validate_generated_cypher(cypher)
        except UnsafeCypherError as exc:
            return {
                "graph_evidence": (),
                "degraded": True,
                "errors": _append(state, f"rejected_cypher: {exc}"),
            }

        limits: RetrievalLimits = state["limits"]
        params = {
            "workspace_id": state["workspace_id"],
            "seed_ids": list(state.get("expansion_seed_ids", ())),
            "limit": limits.graph_row_limit,
        }
        try:
            rows = self.adapter.read_query(cypher, params)
        except AdapterError as exc:
            return {
                "graph_evidence": (),
                "degraded": True,
                "errors": _append(state, f"graph_query_failed: {exc}"),
            }

        allowed = set(state.get("allowed_source_ids", ())) or None
        evidence = tuple(
            EvidenceItem(
                id=str(row[0]),
                source_id=str(row[1]),
                text=str(row[3] or row[2] or ""),
                source_location=str(row[4] or ""),
                score=0.5,
                origin="graph",
            )
            for row in rows
            if allowed is None or str(row[1]) in allowed
        )
        return {"graph_evidence": evidence}

    def _evidence_ranking(self, state: ChatWorkflowState) -> dict[str, Any]:
        combined: dict[str, EvidenceItem] = {}
        for hit in state.get("retrieval_hits", ()):
            combined[hit.id] = EvidenceItem(
                id=hit.id,
                source_id=hit.source_id,
                text=hit.text,
                source_location=hit.source_location,
                score=hit.score,
                origin="retrieval",
            )
        for item in state.get("graph_evidence", ()):
            combined.setdefault(item.id, item)

        limits: RetrievalLimits = state["limits"]
        cap = limits.hybrid_k + limits.graph_row_limit
        ranked = tuple(
            sorted(combined.values(), key=lambda item: (-item.score, item.id))[:cap]
        )
        insufficient = state.get("insufficient_evidence", False) or not ranked
        return {"evidence": ranked, "insufficient_evidence": insufficient}

    def _answer_synthesis(self, state: ChatWorkflowState) -> dict[str, Any]:
        if state.get("cancelled"):
            return {
                "answer": CANCELLED_TEXT,
                "citation_ids": (),
                "errors": _append(state, "cancelled"),
            }

        evidence = state.get("evidence", ())
        errors = list(state.get("errors", ()))
        limits: RetrievalLimits = state["limits"]
        max_attempts = limits.max_provider_retries + 1
        result: ChatAnswer | None = None
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = self.chat_model.synthesize(state["query"], evidence)
                break
            except ProviderTransientError as exc:
                last_exc = exc
                errors.append(f"provider_retry_{attempt}: {exc}")
                if attempt < max_attempts:
                    self.sleep(0.01 * attempt)
        if result is None:
            errors.append(f"provider_exhausted: {last_exc}")
            result = ChatAnswer(text=PROVIDER_UNAVAILABLE_TEXT, citation_ids=())

        return {"answer": result.text, "citation_ids": result.citation_ids, "errors": tuple(errors)}

    def _citation_validation(self, state: ChatWorkflowState) -> dict[str, Any]:
        evidence_by_id = {item.id: item for item in state.get("evidence", ())}
        citation_ids = state.get("citation_ids", ())
        unresolved = [cid for cid in citation_ids if cid not in evidence_by_id]

        if unresolved:
            return {
                "citations": (),
                "answer": INSUFFICIENT_EVIDENCE_TEXT,
                "insufficient_evidence": True,
                "errors": _append(state, f"unresolved_citations: {unresolved}"),
            }

        citations = tuple(
            {
                "evidence_id": evidence_by_id[cid].id,
                "source_id": evidence_by_id[cid].source_id,
                "source_location": evidence_by_id[cid].source_location,
                "origin": evidence_by_id[cid].origin,
            }
            for cid in citation_ids
        )
        return {"citations": citations}

    # -- public API ---------------------------------------------------------

    def ask(self, request: ChatRequest) -> ChatResponse:
        limits = RetrievalLimits.resolve(
            self.config,
            requested_k=request.requested_k,
            requested_graph_row_limit=request.requested_graph_row_limit,
        )
        initial_state: ChatWorkflowState = {
            "workspace_id": request.workspace_id,
            "allowed_source_ids": tuple(request.allowed_source_ids),
            "query": request.query,
            "strategy": request.strategy,
            "limits": limits,
            "scope_valid": True,
            "retrieval_hits": (),
            "expansion_seed_ids": (),
            "expansion_cypher": "",
            "graph_evidence": (),
            "evidence": (),
            "citation_ids": (),
            "citations": (),
            "answer": "",
            "degraded": False,
            "insufficient_evidence": False,
            "errors": (),
            "timings": {},
            "cancelled": request.cancelled,
        }
        final_state = self._graph.invoke(initial_state)
        return ChatResponse(
            workspace_id=request.workspace_id,
            query_id=request.query_id or uuid4().hex,
            answer=final_state.get("answer", ""),
            citations=[dict(item) for item in final_state.get("citations", ())],
            evidence=[item.to_json_dict() for item in final_state.get("evidence", ())],
            degraded=bool(final_state.get("degraded", False)),
            insufficient_evidence=bool(final_state.get("insufficient_evidence", False)),
            strategy=request.strategy,
            errors=list(final_state.get("errors", ())),
            timings=dict(final_state.get("timings", {})),
        )
