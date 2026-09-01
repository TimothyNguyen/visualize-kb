"""Workspace-scoped chat HTTP/SSE contract surface (T11).

Sits directly on top of :class:`~kb_core_ui.rag.workflow.ChatWorkflow` (T9)
and :class:`~kb_core_ui.rag.persistence.ChatHistoryStore` (T10) -- it never
opens a database client of its own and never bypasses either module's own
scoping/validation. Its only job is: build one ``ChatRequest`` per call, turn
one finished ``ChatResponse`` into the frozen JSON/SSE contract shape (see
:func:`chat_contract_payload`), and own the HTTP-facing concerns neither T9
nor T10 needed to know about -- query-id lifecycle, cancellation, per-
workspace stream concurrency limits, suggestions, feedback, and thread
retrieval/cleanup.

Every public method takes ``workspace_id`` first and calls
``self.registry.get(workspace_id)`` before doing anything else, so an
unknown workspace always surfaces as the same ``WorkspaceError`` the
existing management routes already map to 404 -- no separate not-found path
to keep in sync.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4

from kb_core_ui.memory import HashingEmbedder
from kb_core_ui.rag.chat_contract import (
    SSE_EVENT_CANCELLED,
    SSE_EVENT_COMPLETED,
    SSE_EVENT_ERROR,
    SSE_EVENT_HEARTBEAT,
    SSE_EVENT_QUEUED,
    SSE_EVENT_TOKEN,
    TERMINAL_SSE_EVENTS,
    ChatManagerError,
)
from kb_core_ui.rag.chat_memory import ChatMemorySink, NullChatMemorySink
from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.falkordb_adapter import AdapterError, FalkorDBAdapter
from kb_core_ui.rag.indexing import EmbeddingProvider
from kb_core_ui.rag.persistence import ChatHistoryStore, ChatThreadAdapter, validate_thread_id
from kb_core_ui.rag.workflow import (
    CANCELLED_TEXT,
    ChatModel,
    ChatRequest,
    ChatResponse,
    ChatWorkflow,
    FakeChatModel,
)
from kb_core_ui.rag.workspaces import WorkspaceError, WorkspaceRegistry

# --------------------------------------------------------------------------- #
# Contract constants
# --------------------------------------------------------------------------- #

DEFAULT_SUGGESTIONS: tuple[str, ...] = (
    "What does this workspace cover?",
    "Summarize the most recently ingested source.",
    "What are the key entities in this graph?",
    "Which sources mention configuration or setup?",
)

MAX_CHAT_BODY_BYTES = 65_536
DEFAULT_MAX_CONCURRENT_STREAMS_PER_WORKSPACE = 4
_CANCEL_POLL_ATTEMPTS = 15
_CANCEL_POLL_INTERVAL_S = 0.02
_HEARTBEAT_EVERY_POLLS = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# Default, fully-offline embedding provider (no external API key needed)
# --------------------------------------------------------------------------- #


class HashingEmbeddingProvider:
    """Adapts the existing memory-module hashing embedder to the
    ``embed_documents``/``embed_query`` shape ``HybridRetriever`` expects, so
    the default chat manager needs no provider credentials to run."""

    def __init__(self, dim: int = 512) -> None:
        self._embedder = HashingEmbedder(dim=dim)

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._embedder.embed(text).tolist() for text in texts]

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embedder.embed(text).tolist()


# --------------------------------------------------------------------------- #
# Contract payload assembly
# --------------------------------------------------------------------------- #


def derive_source_map(citations: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Citation evidence id -> source metadata, built only from fields the
    workflow's citation_validation node already proved are grounded (T9) --
    never a second lookup that could disagree with what the answer cited."""

    return {
        str(citation["evidence_id"]): {
            "source_id": citation.get("source_id", ""),
            "source_location": citation.get("source_location", ""),
            "origin": citation.get("origin", ""),
        }
        for citation in citations
    }


def _explain_graph(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """A bounded subgraph view built only from evidence the workflow already
    retrieved (T9's ``graph`` origin) -- never an extra database read, so
    this can never diverge from what the answer was actually grounded in."""

    nodes = [
        {
            "id": item["id"],
            "source_id": item["source_id"],
            "label": str(item["text"])[:80],
            "source_location": item["source_location"],
        }
        for item in evidence
        if item.get("origin") == "graph"
    ]
    return {"nodes": nodes, "edges": []}


def chat_contract_payload(
    response_json: Mapping[str, Any],
    *,
    error: str = "",
) -> dict[str, Any]:
    """The frozen T11 JSON/SSE contract shape. Always contains ``answer``,
    ``query_id``, ``workspace_id``, ``context``, ``explain_graph``,
    ``source_map``, ``strategy``, ``degraded`` and ``error``, plus the
    underlying ``citations``/``insufficient_evidence``/``errors``/``timings``
    the workflow already produces -- nothing the workflow proved is thrown
    away going into the wire format. The workflow's ``evidence`` list is
    carried under the contract's own name, ``context``, rather than sent
    twice under both names.

    Takes the workflow's JSON dict rather than a ``ChatResponse`` so a turn
    replayed out of persisted history goes through this exact same function,
    and a client renders live and replayed answers with one type."""

    payload = dict(response_json)
    evidence = list(payload.pop("evidence", ()))
    payload["context"] = evidence
    payload["explain_graph"] = _explain_graph(evidence)
    payload["source_map"] = derive_source_map(payload.get("citations", ()))
    payload["error"] = error
    return payload


def _chunk_answer(text: str) -> list[str]:
    words = [word for word in text.split(" ") if word]
    return words or ([text] if text else [])


# --------------------------------------------------------------------------- #
# Chat manager
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _QueryRecord:
    workspace_id: str
    payload: dict[str, Any]


class ChatManager:
    """HTTP/SSE-facing chat surface bound to one workspace registry + config.

    Builds a fresh :class:`ChatWorkflow` (and its adapter) per call via
    ``adapter_factory``, mirroring ``WorkspaceManager``'s own per-call
    adapter lifecycle (C3: exactly one adapter, closed when the call
    finishes) -- this module never keeps a long-lived adapter around.
    """

    def __init__(
        self,
        registry: WorkspaceRegistry,
        config: RagConfig,
        *,
        adapter_factory: Callable[[str], object] | None = None,
        chat_model_factory: Callable[[], ChatModel] | None = None,
        embeddings: EmbeddingProvider | None = None,
        history_store_factory: Callable[[object], ChatThreadAdapter] | None = None,
        max_concurrent_streams: int = DEFAULT_MAX_CONCURRENT_STREAMS_PER_WORKSPACE,
        max_body_bytes: int = MAX_CHAT_BODY_BYTES,
        suggestion_pool: Sequence[str] = DEFAULT_SUGGESTIONS,
        max_cached_queries: int = 500,
        sleep: Callable[[float], None] = time.sleep,
        chat_memory_sink: ChatMemorySink | None = None,
    ) -> None:
        if max_concurrent_streams < 1:
            raise ValueError("max_concurrent_streams must be positive")
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.registry = registry
        self.config = config
        self.adapter_factory = adapter_factory or (
            lambda workspace_id: FalkorDBAdapter(config, workspace_id)
        )
        if chat_model_factory is None:
            if config.llm_provider not in {"fake", "harness-fake"}:
                raise ValueError(
                    f"unsupported RAG_LLM_PROVIDER {config.llm_provider!r}; "
                    "configure an explicit chat_model_factory"
                )
            chat_model_factory = FakeChatModel
        if embeddings is None:
            if config.embedding_model not in {"fake", "harness-fake"}:
                raise ValueError(
                    f"unsupported RAG_EMBEDDING_MODEL {config.embedding_model!r}; "
                    "configure an explicit embeddings provider"
                )
            embeddings = HashingEmbeddingProvider()
        self.chat_model_factory = chat_model_factory
        self.embeddings = embeddings
        self.history_store_factory = history_store_factory or (
            lambda adapter: ChatHistoryStore(adapter, config=config)
        )
        self.max_concurrent_streams = max_concurrent_streams
        self.max_body_bytes = max_body_bytes
        self.suggestion_pool = tuple(suggestion_pool)
        self.max_cached_queries = max_cached_queries
        self.sleep = sleep
        self.chat_memory_sink = chat_memory_sink or NullChatMemorySink()

        self._sink_errors: list[str] = []
        self._lock = threading.Lock()
        self._active_query_ids: set[str] = set()
        self._cancelled_query_ids: set[str] = set()
        self._concurrent_streams: dict[str, int] = {}
        self._query_cache: dict[str, _QueryRecord] = {}
        self._query_order: list[str] = []
        self._feedback: dict[str, list[dict[str, Any]]] = {}

    # -- shared plumbing --------------------------------------------------

    def _record_memory(self, turn: Any) -> None:
        """Archive one turn. The sink already swallows store failures; this
        guard is for a sink that is itself broken, because no archive problem
        may turn an answered turn into a failed request."""

        try:
            self.chat_memory_sink.record(turn)
        except Exception as exc:  # noqa: BLE001 - a sink must never break a turn
            print(f"chat memory sink raised: {exc}", file=sys.stderr)
            self._sink_errors.append(f"chat_memory: record failed ({exc.__class__.__name__})")

    def _with_sink_errors(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append archive failures to the wire payload's errors.

        Builds a new list rather than mutating in place: the list under
        ``errors`` is the one the workflow's ChatResponse owns.
        """

        drained = self._sink_errors + list(self.chat_memory_sink.drain_errors())
        self._sink_errors = []
        if drained:
            payload["errors"] = list(payload.get("errors", ())) + drained
        return payload

    def check_body_size(self, body: bytes) -> None:
        if len(body) > self.max_body_bytes:
            raise ChatManagerError(413, f"request body exceeds {self.max_body_bytes} bytes")

    def _with_adapter(self, workspace_id: str, operation: Callable[[Any], Any]) -> Any:
        adapter = self.adapter_factory(workspace_id)
        try:
            return operation(adapter)
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()

    def _ask(
        self,
        adapter: Any,
        *,
        workspace_id: str,
        query: str,
        allowed_source_ids: Sequence[str],
        strategy: str,
        requested_k: int | None,
        requested_graph_row_limit: int | None,
        query_id: str,
        cancelled: bool,
    ) -> ChatResponse:
        workflow = ChatWorkflow(
            adapter=adapter,
            registry=self.registry,
            chat_model=self.chat_model_factory(),
            embeddings=self.embeddings,
            config=self.config,
        )
        request = ChatRequest(
            workspace_id=workspace_id,
            query=query,
            allowed_source_ids=tuple(allowed_source_ids),
            strategy=strategy,
            query_id=query_id,
            requested_k=requested_k,
            requested_graph_row_limit=requested_graph_row_limit,
            cancelled=cancelled,
        )
        return workflow.ask(request)

    def _cache_query(self, query_id: str, workspace_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._query_cache[query_id] = _QueryRecord(workspace_id=workspace_id, payload=payload)
            self._query_order.append(query_id)
            while len(self._query_order) > self.max_cached_queries:
                stale = self._query_order.pop(0)
                self._query_cache.pop(stale, None)
                self._feedback.pop(stale, None)

    def _cached(self, workspace_id: str, query_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._query_cache.get(query_id)
        if record is None or record.workspace_id != workspace_id:
            raise ChatManagerError(404, f"unknown query id: {query_id}")
        return record.payload

    def _is_cancelled(self, query_id: str) -> bool:
        with self._lock:
            return query_id in self._cancelled_query_ids

    # -- complete (non-streaming) chat -------------------------------------

    def ask(
        self,
        workspace_id: str,
        *,
        query: str,
        thread_id: str = "",
        allowed_source_ids: Sequence[str] = (),
        strategy: str = "auto",
        requested_k: int | None = None,
        requested_graph_row_limit: int | None = None,
        query_id: str = "",
    ) -> dict[str, Any]:
        self.registry.get(workspace_id)
        if thread_id:
            validate_thread_id(thread_id)
        qid = query_id or uuid4().hex

        with self._lock:
            if qid in self._active_query_ids:
                raise ChatManagerError(409, f"query id already in progress: {qid}")
            self._active_query_ids.add(qid)
        try:
            def operation(adapter: Any) -> ChatResponse:
                response = self._ask(
                    adapter,
                    workspace_id=workspace_id,
                    query=query,
                    allowed_source_ids=allowed_source_ids,
                    strategy=strategy,
                    requested_k=requested_k,
                    requested_graph_row_limit=requested_graph_row_limit,
                    query_id=qid,
                    cancelled=False,
                )
                if thread_id:
                    turn = self.history_store_factory(adapter).write_turn(
                        thread_id, query, response
                    )
                    self._record_memory(turn)
                return response

            response = self._with_adapter(workspace_id, operation)
        finally:
            with self._lock:
                self._active_query_ids.discard(qid)

        payload = self._with_sink_errors(chat_contract_payload(response.to_json_dict()))
        self._cache_query(qid, workspace_id, payload)
        return payload

    # -- SSE stream ---------------------------------------------------------

    def open_stream(
        self,
        workspace_id: str,
        *,
        query: str,
        thread_id: str = "",
        allowed_source_ids: Sequence[str] = (),
        strategy: str = "auto",
        requested_k: int | None = None,
        requested_graph_row_limit: int | None = None,
        query_id: str = "",
    ) -> Callable[[], Iterator[tuple[str, dict[str, Any]]]]:
        """Validates and reserves stream capacity synchronously (so a 409/429
        can still be a normal JSON error response, before any SSE bytes are
        written), then returns a zero-arg factory yielding ``(event, data)``
        pairs. This module has no dependency on the HTTP/SSE wire format
        (avoids a rag<->server import cycle, since ``server.app`` already
        depends on this module) -- the caller (``server.app``'s chat route)
        frames each pair into an SSE byte chunk via
        ``server.wire.format_sse_event``. No retrieval/provider work happens
        until that factory is actually called by the transport."""

        self.registry.get(workspace_id)
        if thread_id:
            validate_thread_id(thread_id)
        qid = query_id or uuid4().hex

        with self._lock:
            if qid in self._active_query_ids:
                raise ChatManagerError(409, f"query id already in progress: {qid}")
            in_flight = self._concurrent_streams.get(workspace_id, 0)
            if in_flight >= self.max_concurrent_streams:
                raise ChatManagerError(
                    429,
                    f"too many concurrent chat streams for workspace {workspace_id} "
                    f"(limit {self.max_concurrent_streams})",
                )
            self._active_query_ids.add(qid)
            self._concurrent_streams[workspace_id] = in_flight + 1

        def events() -> Iterator[tuple[str, dict[str, Any]]]:
            try:
                yield SSE_EVENT_QUEUED, {"query_id": qid, "workspace_id": workspace_id}

                # Give a concurrently issued /chat/cancel a bounded window to
                # land before work starts -- disconnect/cancel propagation
                # (V-cancel), not a retry loop.
                for attempt in range(_CANCEL_POLL_ATTEMPTS):
                    if self._is_cancelled(qid):
                        break
                    if attempt % _HEARTBEAT_EVERY_POLLS == 0:
                        yield SSE_EVENT_HEARTBEAT, {}
                    self.sleep(_CANCEL_POLL_INTERVAL_S)
                if self._is_cancelled(qid):
                    yield SSE_EVENT_CANCELLED, {"query_id": qid, "workspace_id": workspace_id}
                    return

                try:
                    def operation(adapter: Any) -> ChatResponse:
                        response = self._ask(
                            adapter,
                            workspace_id=workspace_id,
                            query=query,
                            allowed_source_ids=allowed_source_ids,
                            strategy=strategy,
                            requested_k=requested_k,
                            requested_graph_row_limit=requested_graph_row_limit,
                            query_id=qid,
                            cancelled=self._is_cancelled(qid),
                        )
                        # A turn whose answer is the cancelled marker (or a
                        # cancel that lands mid-workflow) is never persisted
                        # as a complete turn (V10) -- only a genuinely
                        # finished, non-cancelled answer is written.
                        if (
                            thread_id
                            and not self._is_cancelled(qid)
                            and response.answer != CANCELLED_TEXT
                        ):
                            turn = self.history_store_factory(adapter).write_turn(
                                thread_id, query, response
                            )
                            self._record_memory(turn)
                        return response

                    response = self._with_adapter(workspace_id, operation)
                except (AdapterError, OSError) as exc:
                    yield SSE_EVENT_ERROR, {
                        "query_id": qid,
                        "workspace_id": workspace_id,
                        "status": 503,
                        "message": str(exc),
                    }
                    return
                except WorkspaceError as exc:
                    yield SSE_EVENT_ERROR, {
                        "query_id": qid,
                        "workspace_id": workspace_id,
                        "status": 400,
                        "message": str(exc),
                    }
                    return

                if self._is_cancelled(qid) or response.answer == CANCELLED_TEXT:
                    yield SSE_EVENT_CANCELLED, {"query_id": qid, "workspace_id": workspace_id}
                    return

                for token in _chunk_answer(response.answer):
                    yield SSE_EVENT_TOKEN, {"query_id": qid, "text": token}

                # One terminal completion event, sent only after the turn
                # (if any) has already been durably persisted above -- a
                # disconnect after this point can never lose a completed
                # turn, and nothing before this point can ever be mistaken
                # for a complete one.
                payload = self._with_sink_errors(chat_contract_payload(response.to_json_dict()))
                self._cache_query(qid, workspace_id, payload)
                yield SSE_EVENT_COMPLETED, payload
            finally:
                with self._lock:
                    self._active_query_ids.discard(qid)
                    self._cancelled_query_ids.discard(qid)
                    self._concurrent_streams[workspace_id] = max(
                        0, self._concurrent_streams.get(workspace_id, 1) - 1
                    )

        return events

    # -- cancellation ---------------------------------------------------

    def cancel(self, workspace_id: str, query_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        with self._lock:
            if query_id in self._active_query_ids:
                self._cancelled_query_ids.add(query_id)
                return {"query_id": query_id, "workspace_id": workspace_id, "cancelled": True}
            cached = self._query_cache.get(query_id)
        if cached is not None:
            if cached.workspace_id != workspace_id:
                raise ChatManagerError(404, f"unknown query id: {query_id}")
            return {
                "query_id": query_id,
                "workspace_id": workspace_id,
                "cancelled": False,
                "reason": "already completed",
            }
        raise ChatManagerError(404, f"unknown query id: {query_id}")

    # -- suggestions and feedback ----------------------------------------

    def suggestions(self, workspace_id: str, *, thread_id: str = "") -> dict[str, Any]:
        self.registry.get(workspace_id)
        recent: list[str] = []
        if thread_id:
            validate_thread_id(thread_id)
            turns = self._with_adapter(
                workspace_id,
                lambda adapter: self.history_store_factory(adapter).list_turns(thread_id),
            )
            recent = [turn.query for turn in turns[-3:]]
        return {
            "workspace_id": workspace_id,
            "suggestions": list(self.suggestion_pool),
            "recent_queries": recent,
        }

    _VALID_RATINGS = frozenset({"up", "down"})

    def feedback(
        self, workspace_id: str, *, query_id: str, rating: str, comment: str = ""
    ) -> dict[str, Any]:
        self.registry.get(workspace_id)
        if rating not in self._VALID_RATINGS:
            raise ChatManagerError(400, "rating must be 'up' or 'down'")
        # Confirms the query id is real and belongs to this workspace before
        # accepting feedback for it -- defense against recording feedback
        # against another workspace's answer.
        self._cached(workspace_id, query_id)
        entry = {
            "query_id": query_id,
            "workspace_id": workspace_id,
            "rating": rating,
            "comment": comment,
            "created_at": _now(),
        }
        with self._lock:
            self._feedback.setdefault(query_id, []).append(entry)
        return entry

    # -- source map and graph explanation --------------------------------

    def source_map(self, workspace_id: str, query_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        payload = self._cached(workspace_id, query_id)
        return {
            "workspace_id": workspace_id,
            "query_id": query_id,
            "source_map": payload["source_map"],
        }

    def explain_graph(self, workspace_id: str, query_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        payload = self._cached(workspace_id, query_id)
        return {
            "workspace_id": workspace_id,
            "query_id": query_id,
            "explain_graph": payload["explain_graph"],
        }

    # -- thread retrieval and cleanup -------------------------------------

    def list_thread(self, workspace_id: str, thread_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        validate_thread_id(thread_id)
        turns = self._with_adapter(
            workspace_id,
            lambda adapter: self.history_store_factory(adapter).list_turns(thread_id),
        )
        if not turns:
            raise ChatManagerError(404, f"thread not found: {thread_id}")
        replayed = []
        for turn in turns:
            record = turn.to_json_dict()
            record["response"] = chat_contract_payload(record["response"])
            replayed.append(record)
        return {"workspace_id": workspace_id, "thread_id": thread_id, "turns": replayed}

    def delete_thread(self, workspace_id: str, thread_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        validate_thread_id(thread_id)
        self._with_adapter(
            workspace_id,
            lambda adapter: self.history_store_factory(adapter).delete_thread(thread_id),
        )
        self.chat_memory_sink.delete_thread(workspace_id, thread_id)
        return {"workspace_id": workspace_id, "thread_id": thread_id, "deleted": True}

    def delete_all_threads(self, workspace_id: str) -> dict[str, Any]:
        self.registry.get(workspace_id)
        removed = self._with_adapter(
            workspace_id,
            lambda adapter: self.history_store_factory(adapter).cleanup_workspace(),
        )
        self.chat_memory_sink.delete_workspace(workspace_id)
        return {"workspace_id": workspace_id, "deleted_threads": removed}
