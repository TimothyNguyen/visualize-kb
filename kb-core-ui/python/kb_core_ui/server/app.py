"""The REST API from API_CONTRACT.md — the Python side of internal/server/.

Every route, status code and error string is a line-for-line port of
server.go, memory.go and bots.go, because the harness compares Go and
Python responses body-for-body.
"""

from __future__ import annotations

import mimetypes
import os
import threading
from typing import Any, Callable, Iterable

from kb_core_ui import jsonx
from kb_core_ui.bots.registry import REGISTRY
from kb_core_ui.bots.runner import MissingArgError, Runner, UnknownBotError
from kb_core_ui.errors import KbError
from kb_core_ui.memory import VALID_KINDS
from kb_core_ui.memory import Store as MemoryStore
from kb_core_ui.memory import now as memory_now
from kb_core_ui.rag.chat_contract import SSE_EVENT_HEARTBEAT, ChatManagerError
from kb_core_ui.rag.agui import AgUiError, agui_stream, parse_run_input
from kb_core_ui.rag.falkordb_adapter import AdapterError
from kb_core_ui.rag.workspaces import WorkspaceError
from kb_core_ui.server.mux import Mux, clean_path
from kb_core_ui.server.wire import (
    SSE_HEARTBEAT_FRAME,
    Request,
    Response,
    format_sse_event,
    path_unescape,
    write_error,
    write_json,
    write_sse,
    write_text,
)
from kb_core_ui.store import Store

API_ONLY_INDEX = (
    "kb-core-ui API server is running. Build web/ and pass --web-dir to serve the UI here.\n"
)


def _non_nil(items: list | None) -> list:
    """server.go's nonNil: an empty result must marshal as [] not null — the
    contract types these as arrays and the frontend maps over them
    unconditionally."""
    return [] if items is None else items


def _json_list(items: list | None) -> list[Any]:
    return [item.to_json_dict() for item in _non_nil(items)]


def _valid_mem_kind(kind: str) -> bool:
    # "" means "no filter" for list/search.
    return kind == "" or kind in VALID_KINDS


class Server:
    """Holds everything the handlers need. web_dir may be "" (no UI at "/"),
    runner may be None (no bot endpoints) and memory may be None (no memory
    endpoints) — the graph API always works regardless."""

    def __init__(
        self,
        store: Store,
        repo_root: str,
        web_dir: str = "",
        runner: Runner | None = None,
        memory: MemoryStore | None = None,
        workspace_manager: object | None = None,
        chat_manager: object | None = None,
    ) -> None:
        self.store = store
        self.repo_root = repo_root
        self.web_dir = web_dir
        self.runner = runner
        self.memory = memory
        self.workspace_manager = workspace_manager
        self.chat_manager = chat_manager
        self.mux = Mux()
        # Go's *sql.DB is a connection pool safe for concurrent use; a
        # sqlite3.Connection is not. Requests arrive on separate threads, so
        # handler dispatch is serialized here. Bot runs execute on their own
        # threads and never touch the store, so they stay unblocked.
        self._lock = threading.RLock()
        self._routes()

    # ---- routing -------------------------------------------------------

    def _routes(self) -> None:
        self.mux.handle("GET /api/tree", self.handle_tree)
        self.mux.handle("GET /api/graph", self.handle_graph)
        self.mux.handle("GET /api/graph/subgraph", self.handle_subgraph)
        self.mux.handle("GET /api/search", self.handle_search)
        self.mux.handle("GET /api/source", self.handle_source)
        self.mux.handle("GET /api/stats", self.handle_stats)
        self.mux.handle("GET /api/files/", self.handle_file_symbols)
        self.mux.handle("GET /api/symbols/", self.handle_symbols)

        if self.runner is not None:
            self.mux.handle("GET /api/bots", self.handle_bots)
            self.mux.handle("POST /api/bots/", self.handle_bot_run)  # /api/bots/:name/run
            self.mux.handle("GET /api/bots/runs", self.handle_bot_runs)
            self.mux.handle("GET /api/bots/runs/", self.handle_bot_run_by_id)

        if self.memory is not None:
            self.mux.handle("GET /api/memory", self.handle_memory_list)
            self.mux.handle("GET /api/memory/search", self.handle_memory_search)
            self.mux.handle("POST /api/memory", self.handle_memory_add)
            self.mux.handle("DELETE /api/memory/", self.handle_memory_delete)

        if self.workspace_manager is not None:
            for method in ("GET", "POST", "DELETE"):
                self.mux.handle(f"{method} /api/rag/workspaces", self.handle_rag_workspaces)
                self.mux.handle(f"{method} /api/rag/workspaces/", self.handle_rag_workspaces)
        if self.chat_manager is not None:
            self.mux.handle("POST /api/rag/agent", self.handle_rag_agent)

        self.mux.handle("/", self.handle_root)

    def serve(self, req: Request) -> Response:
        def dispatch(r: Request) -> Response:
            with self._lock:
                return self.mux.dispatch(r)

        return _with_cors(dispatch, req)

    # ---- graph ---------------------------------------------------------

    def handle_tree(self, req: Request) -> Response:
        try:
            tree = self.store.tree()
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(tree.to_json_dict())

    def handle_file_symbols(self, req: Request) -> Response:
        """GET /api/files/*path/symbols. Go's ServeMux cannot express a
        wildcard followed by a literal suffix, so the path is split here."""
        rest = _trim_prefix(req.path, "/api/files/")
        if not rest.endswith("/symbols"):
            return Response.not_found()
        path = rest[: -len("/symbols")]
        if path.endswith("/"):
            path = path[:-1]
        if path == "":
            return write_error(400, "missing file path")
        try:
            syms = self.store.symbols_in_file(path)
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(_json_list(syms))

    def handle_symbols(self, req: Request) -> Response:
        """GET /api/symbols/:id and its /members, /calls, /callers suffixes.

        Symbol ids embed a file path, so the client percent-encodes their
        slashes as %2F. Splitting on the decoded path would unescape those
        back to "/" and corrupt the id/suffix split — hence raw_path."""
        rest = _trim_prefix(req.raw_path, "/api/symbols/")
        id_escaped, sep, suffix = rest.partition("/")
        has_suffix = bool(sep)
        try:
            symbol_id = path_unescape(id_escaped)
        except ValueError:
            return write_error(400, "invalid symbol id encoding")

        try:
            if not has_suffix:
                sym = self.store.symbol(symbol_id)
                if sym is None:
                    return write_error(404, "symbol not found: " + symbol_id)
                return write_json(sym.to_json_dict())
            if suffix == "members":
                return write_json(_json_list(self.store.members(symbol_id)))
            if suffix == "calls":
                return write_json(_json_list(self.store.calls(symbol_id)))
            if suffix == "callers":
                return write_json(_json_list(self.store.callers(symbol_id)))
        except KbError as exc:
            return write_error(500, str(exc))
        return Response.not_found()

    def handle_graph(self, req: Request) -> Response:
        try:
            nodes, edges = self.store.full_graph()
        except KbError as exc:
            return write_error(500, str(exc))
        # Go marshals a map here, and encoding/json sorts map keys.
        return write_json({"edges": _json_list(edges), "nodes": _json_list(nodes)})

    def handle_subgraph(self, req: Request) -> Response:
        symbol = req.get_query("symbol")
        if symbol == "":
            return write_error(400, "missing symbol query param")
        depth = 2
        raw_depth = req.get_query("depth")
        if raw_depth != "":
            n = _atoi(raw_depth)
            if n is None or n < 1:
                return write_error(400, "invalid depth")
            depth = n
        try:
            if self.store.symbol(symbol) is None:
                return write_error(404, "symbol not found: " + symbol)
            nodes, edges = self.store.subgraph(symbol, depth)
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(
            {"center": symbol, "edges": _json_list(edges), "nodes": _json_list(nodes)}
        )

    def handle_search(self, req: Request) -> Response:
        try:
            results = self.store.search(req.get_query("q"), req.get_query("kind"))
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(_json_list(results))

    def handle_source(self, req: Request) -> Response:
        file = req.get_query("file")
        if file == "":
            return write_error(400, "missing file query param")
        start = _atoi(req.get_query("start"))
        end = _atoi(req.get_query("end"))
        if start is None or end is None or start < 1 or end < start:
            return write_error(400, "invalid start/end")

        # filepath.Join concatenates *then* cleans, so an absolute or
        # ../-laden `file` still resolves against the repo root before the
        # containment check runs. os.path.join would drop the root entirely.
        full = os.path.normpath(self.repo_root + os.sep + file.replace("/", os.sep))
        if not full.startswith(os.path.normpath(self.repo_root) + os.sep):
            return write_error(400, "file path escapes repo root")
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError:
            return write_error(404, "file not found: " + file)

        # Go splits the raw bytes on "\n" and lets the JSON encoder replace
        # any invalid UTF-8 with U+FFFD.
        all_lines = data.decode("utf-8", errors="replace").split("\n")
        if start > len(all_lines):
            return write_json({"filePath": file, "lines": [], "startLine": start})
        if end > len(all_lines):
            end = len(all_lines)
        return write_json(
            {"filePath": file, "lines": all_lines[start - 1 : end], "startLine": start}
        )

    def handle_stats(self, req: Request) -> Response:
        try:
            stats = self.store.stats()
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(
            {
                "edges": stats.edges,
                "files": stats.files,
                "languages": stats.languages,
                "symbols": stats.symbols,
            }
        )

    # ---- bots ----------------------------------------------------------

    def handle_bots(self, req: Request) -> Response:
        defs = []
        for definition in REGISTRY:
            payload = definition.to_json_dict()
            # Normalize Args to a non-nil slice: the contract types it as
            # BotArg[] and the dashboard maps over it unconditionally.
            if payload.get("args") is None:
                payload["args"] = []
            defs.append(payload)
        return write_json(defs)

    def handle_bot_run(self, req: Request) -> Response:
        rest = _trim_prefix(req.path, "/api/bots/")
        name, sep, suffix = rest.partition("/")
        if not sep or suffix != "run" or name == "":
            return write_error(404, "not found")

        body: dict[str, Any] = {}
        if req.body:
            # An empty body is fine (bots with no args); a decode failure is
            # ignored the same way Go ignores the EOF from an empty reader.
            try:
                decoded = jsonx.loads(req.body.decode("utf-8"))
                if isinstance(decoded, dict):
                    body = decoded
            except (ValueError, UnicodeDecodeError):
                body = {}
        args = body.get("args") or {}

        try:
            run = self.runner.start(name, args)
        except UnknownBotError as exc:
            return write_error(404, str(exc))
        except MissingArgError as exc:
            return write_error(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - mirrors Go's default branch
            return write_error(500, str(exc))
        return write_json(run.to_json_dict())

    def handle_bot_runs(self, req: Request) -> Response:
        return write_json([r.summary_json_dict() for r in _non_nil(self.runner.list())])

    def handle_bot_run_by_id(self, req: Request) -> Response:
        run_id = _trim_prefix(req.path, "/api/bots/runs/")
        if run_id == "":
            return write_error(400, "missing run id")
        run = self.runner.get(run_id)
        if run is None:
            return write_error(404, "run not found: " + run_id)
        return write_json(run.to_json_dict())

    # ---- memory --------------------------------------------------------

    def handle_memory_list(self, req: Request) -> Response:
        kind = req.get_query("kind")
        if not _valid_mem_kind(kind):
            return write_error(400, "invalid kind")
        try:
            entries = self.memory.list(kind)
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(_json_list(entries))

    def handle_memory_search(self, req: Request) -> Response:
        q = req.get_query("q")
        kind = req.get_query("kind")
        if not _valid_mem_kind(kind):
            return write_error(400, "invalid kind")
        top = 5
        raw_top = req.get_query("top")
        if raw_top != "":
            n = _atoi(raw_top)
            if n is not None and n > 0:
                top = n
        try:
            hits = self.memory.search(q, kind, top)
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(_json_list(hits))

    def handle_memory_add(self, req: Request) -> Response:
        try:
            body = jsonx.loads(req.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return write_error(400, "invalid JSON body")
        if not isinstance(body, dict):
            return write_error(400, "invalid JSON body")

        kind = _json_string(body, "kind")
        title = _json_string(body, "title")
        text = _json_string(body, "text")
        source = _json_string(body, "source")

        if title == "" or text == "":
            return write_error(400, "title and text are required")
        # An empty kind is a valid filter for search, but a real entry needs one.
        if kind == "" or not _valid_mem_kind(kind):
            return write_error(
                400, "invalid kind (want: rule, lesson, business, overview, reference)"
            )
        try:
            entry = self.memory.add(kind, title, text, source, memory_now())
        except KbError as exc:
            return write_error(500, str(exc))
        return write_json(entry.to_json_dict())

    def handle_memory_delete(self, req: Request) -> Response:
        entry_id = _trim_prefix(req.path, "/api/memory/")
        if entry_id == "":
            return write_error(400, "missing id")
        try:
            removed = self.memory.remove(entry_id)
        except KbError as exc:
            return write_error(500, str(exc))
        if not removed:
            return write_error(404, "no memory with id " + entry_id)
        return write_json({"removed": True})

    # ---- GraphRAG workspace management --------------------------------

    def handle_rag_agent(self, req: Request) -> Response:
        try:
            run = parse_run_input(_json_object(req.body))
            self.workspace_manager.registry.get(run.workspace_id)
        except AgUiError as exc:
            return write_error(400, str(exc))
        except WorkspaceError as exc:
            return write_error(404, str(exc))
        return write_sse(lambda: agui_stream(self.chat_manager, run))

    def handle_rag_workspaces(self, req: Request) -> Response:
        rest = _trim_prefix(req.path, "/api/rag/workspaces").strip("/")
        parts = rest.split("/") if rest else []
        manager = self.workspace_manager
        try:
            if not parts:
                if req.method == "GET":
                    return write_json(manager.list_workspaces())
                if req.method == "POST":
                    body = _json_object(req.body)
                    return write_json(
                        manager.create_workspace(
                            _json_string(body, "id"), _json_string(body, "name")
                        ),
                        status=201,
                    )
            workspace_id = parts[0] if parts else ""
            if len(parts) == 1 and req.method == "DELETE":
                return write_json(manager.delete_workspace(workspace_id))
            if len(parts) == 2 and parts[1] == "health" and req.method == "GET":
                return write_json(manager.health(workspace_id))
            if len(parts) == 2 and parts[1] == "stats" and req.method == "GET":
                return write_json(manager.stats(workspace_id))
            if len(parts) == 2 and parts[1] == "context" and req.method == "GET":
                raw_limit = req.get_query("limit") or "50"
                limit = _atoi(raw_limit)
                if limit is None:
                    raise WorkspaceError("context limit must be an integer")
                return write_json(
                    manager.graph_context(
                        workspace_id,
                        source_ids=req.query.get("source", []),
                        limit=limit,
                    )
                )
            if len(parts) == 2 and parts[1] == "sources" and req.method == "POST":
                body = _json_object(req.body)
                return write_json(
                    manager.add_source(
                        workspace_id,
                        _json_string(body, "id"),
                        _json_string(body, "kind"),
                        _json_string(body, "uri"),
                        _json_string(body, "ref"),
                    ),
                    status=201,
                )
            if len(parts) == 3 and parts[1] == "sources" and req.method == "DELETE":
                return write_json(manager.remove_source(workspace_id, parts[2]))
            if len(parts) == 4 and parts[1] == "sources" and req.method == "POST":
                if parts[3] == "ingestions":
                    return write_json(manager.start_ingestion(workspace_id, parts[2]), status=202)
                if parts[3] == "refresh":
                    return write_json(manager.refresh_source(workspace_id, parts[2]), status=202)
            if len(parts) == 3 and parts[1] == "runs" and req.method == "GET":
                return write_json(manager.get_run(workspace_id, parts[2]))
            if (
                len(parts) == 4
                and parts[1] == "runs"
                and parts[3] == "cancel"
                and req.method == "POST"
            ):
                return write_json(manager.cancel_ingestion(workspace_id, parts[2]))
            if len(parts) >= 2 and parts[1] == "chat":
                return self._handle_chat(req, workspace_id, parts[2:])
        except ChatManagerError as exc:
            return write_error(exc.status, str(exc))
        except WorkspaceError as exc:
            status = 404 if "does not exist" in str(exc) else 400
            return write_error(status, str(exc))
        except (AdapterError, OSError) as exc:
            return write_error(503, str(exc))
        except KeyError as exc:
            return write_error(404, f"resource not found: {exc.args[0]}")
        except ValueError as exc:
            return write_error(400, str(exc))
        return write_error(404, "not found")

    # ---- GraphRAG chat (T11) --------------------------------------------

    def _handle_chat(self, req: Request, workspace_id: str, sub: list[str]) -> Response:
        """``sub`` is the path after ``/api/rag/workspaces/{id}/chat``, e.g.
        ``[]`` for the base route or ``["threads", "t1"]``. Raised errors
        propagate to ``handle_rag_workspaces``'s shared exception mapping."""

        chat = self.chat_manager
        if chat is None:
            return write_error(404, "not found")
        leaf = sub[0] if sub else ""

        if leaf == "" and req.method == "POST":
            chat.check_body_size(req.body)
            body = _json_object(req.body)
            query = _json_string(body, "query")
            if query == "":
                return write_error(400, "query is required")
            payload = chat.ask(
                workspace_id,
                query=query,
                thread_id=_json_string(body, "thread_id"),
                allowed_source_ids=_json_string_list(body, "allowed_source_ids"),
                strategy=_json_string(body, "strategy") or "auto",
                requested_k=_json_int(body, "requested_k"),
                requested_graph_row_limit=_json_int(body, "requested_graph_row_limit"),
                query_id=_json_string(body, "query_id"),
            )
            return write_json(payload)

        if leaf == "stream" and req.method == "GET":
            query = req.get_query("query")
            if query == "":
                return write_error(400, "query is required")
            domain_events = chat.open_stream(
                workspace_id,
                query=query,
                thread_id=req.get_query("thread_id"),
                allowed_source_ids=req.query.get("allowed_source_ids", []),
                strategy=req.get_query("strategy") or "auto",
                requested_k=_atoi_or_none(req.get_query("requested_k")),
                requested_graph_row_limit=_atoi_or_none(req.get_query("requested_graph_row_limit")),
                query_id=req.get_query("query_id"),
            )

            def framed() -> Iterable[bytes]:
                for event, data in domain_events():
                    if event == SSE_EVENT_HEARTBEAT:
                        yield SSE_HEARTBEAT_FRAME
                    else:
                        yield format_sse_event(event, data)

            return write_sse(framed)

        if leaf == "cancel" and req.method == "POST":
            body = _json_object(req.body)
            query_id = _json_string(body, "query_id")
            if query_id == "":
                return write_error(400, "query_id is required")
            return write_json(chat.cancel(workspace_id, query_id))

        if leaf == "suggestions" and req.method == "GET":
            return write_json(chat.suggestions(workspace_id, thread_id=req.get_query("thread_id")))

        if leaf == "feedback" and req.method == "POST":
            body = _json_object(req.body)
            query_id = _json_string(body, "query_id")
            if query_id == "":
                return write_error(400, "query_id is required")
            return write_json(
                chat.feedback(
                    workspace_id,
                    query_id=query_id,
                    rating=_json_string(body, "rating"),
                    comment=_json_string(body, "comment"),
                )
            )

        if leaf == "source_map" and req.method == "GET":
            query_id = req.get_query("query_id")
            if query_id == "":
                return write_error(400, "query_id is required")
            return write_json(chat.source_map(workspace_id, query_id))

        if leaf == "explain_graph" and req.method == "GET":
            query_id = req.get_query("query_id")
            if query_id == "":
                return write_error(400, "query_id is required")
            return write_json(chat.explain_graph(workspace_id, query_id))

        if leaf == "threads":
            if len(sub) == 1 and req.method == "DELETE":
                return write_json(chat.delete_all_threads(workspace_id))
            if len(sub) == 2 and req.method == "GET":
                return write_json(chat.list_thread(workspace_id, sub[1]))
            if len(sub) == 2 and req.method == "DELETE":
                return write_json(chat.delete_thread(workspace_id, sub[1]))

        return write_error(404, "not found")

    # ---- static UI -----------------------------------------------------

    def handle_root(self, req: Request) -> Response:
        if self.web_dir == "":
            if req.path == "/":
                return write_text(API_ONLY_INDEX)
            return Response.not_found()
        return self._serve_spa(req)

    def _serve_spa(self, req: Request) -> Response:
        """Static files, falling back to index.html for any path that is not a
        real file — required for a client-side-routed SPA."""
        rel = clean_path(req.path).lstrip("/").replace("/", os.sep)
        full = os.path.normpath(os.path.join(self.web_dir, rel))
        if not os.path.isfile(full):
            full = os.path.join(self.web_dir, "index.html")
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError:
            return Response.not_found()
        return Response(status=200, body=data, headers={"Content-Type": _content_type(full)})


# ---- helpers -----------------------------------------------------------


def _content_type(path: str) -> str:
    """http.ServeFile's Content-Type, which comes from Go's mime package.

    On Windows that package reads the same registry Python's mimetypes does,
    so both agree on the raw type (.js is application/javascript here but
    text/javascript on a stock Linux table) — hardcoding a table would make
    the port disagree with Go on whichever platform it was not written for.

    Go's setExtensionType then appends charset=utf-8 to any text/* type that
    lacks one, which is why .css comes back as "text/css; charset=utf-8"
    while .js keeps its bare application/javascript.
    """
    guessed, _ = mimetypes.guess_type(path)
    if guessed is None:
        # http.ServeFile falls back to sniffing the first 512 bytes;
        # DetectContentType's default for anything unrecognized.
        return "application/octet-stream"
    if guessed.startswith("text/") and "charset=" not in guessed:
        return guessed + "; charset=utf-8"
    return guessed


def _trim_prefix(s: str, prefix: str) -> str:
    return s[len(prefix) :] if s.startswith(prefix) else s


def _atoi(raw: str) -> int | None:
    """strconv.Atoi: only an optionally-signed run of ASCII digits parses.
    Python's int() would also accept " 12 ", "1_2" and Unicode digits."""
    body = raw[1:] if raw[:1] in ("+", "-") else raw
    if not body.isascii() or not body.isdigit():
        return None
    return int(raw)


def _json_string(body: dict, key: str) -> str:
    """Go decodes into a string field, so a missing key and a JSON null both
    leave the zero value."""
    value = body.get(key)
    return value if isinstance(value, str) else ""


def _json_string_list(body: dict, key: str) -> list[str]:
    value = body.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _json_int(body: dict, key: str) -> int | None:
    value = body.get(key)
    # bool is an int subclass; a JSON true/false is never a valid limit.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _atoi_or_none(raw: str) -> int | None:
    return _atoi(raw) if raw != "" else None


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = jsonx.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise WorkspaceError("invalid JSON body") from None
    if not isinstance(value, dict):
        raise WorkspaceError("invalid JSON body")
    return value


def _with_cors(handler: Callable[[Request], Response], req: Request) -> Response:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    if req.method == "OPTIONS":
        return Response(status=204, body=b"", headers=headers)
    resp = handler(req)
    return Response(
        status=resp.status,
        body=resp.body,
        headers={**headers, **resp.headers},
        stream=resp.stream,
    )
