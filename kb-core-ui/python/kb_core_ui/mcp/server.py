"""Exposes the code graph to AI agents over MCP — the Python side of
internal/mcp/server.go.

Every tool name, description and parameter string is a copy of the Go
original: they are served verbatim through tools/list, which the harness
compares against a recorded baseline.
"""

from __future__ import annotations

import os

from kb_core_ui.errors import KbError, os_error_text
from kb_core_ui.mcp.protocol import PROTOCOL_VERSION, JsonRpcError, METHOD_NOT_FOUND
from kb_core_ui.mcp.tools import (
    Param,
    Registry,
    Tool,
    ToolResult,
    error_from_exc,
    error_result,
    json_result,
    parse_int,
    parse_string,
    text_result,
)
from kb_core_ui.memory import VALID_KINDS
from kb_core_ui.memory import Store as MemoryStore
from kb_core_ui.memory import now as memory_now
from kb_core_ui.store import Store

SERVER_NAME = "kb-core-ui"
SERVER_VERSION = "0.1.0"

SEARCH_SYMBOL_DESC = (
    "Search the code graph for symbols (functions, methods, classes, consts, vars) by name "
    "substring. Use this instead of grepping files to find where something is declared."
)
GET_SYMBOL_DESC = (
    "Get full detail for one symbol by id: signature, params, returns, doc comment, file path "
    "and line range. Use this before reading a file to see if the graph already answers the "
    "question."
)
GET_FILE_SYMBOLS_DESC = (
    "List the top-level symbols (functions, classes, consts, vars) declared in one file, with "
    "their ids and line ranges — a table of contents for the file without reading it."
)
GET_CALLEES_DESC = (
    "List what a symbol calls or references — trace execution forward from a function."
)
GET_CALLERS_DESC = (
    "List what calls or references a symbol — trace execution backward to a function, e.g. to "
    "find every caller before changing its signature."
)
GET_FILE_SLICE_DESC = (
    "Read exact source lines from a file by line range — use this instead of reading the whole "
    "file once get_symbol/get_file_symbols gives you the line range you need."
)
GET_TREE_DESC = "Get the repo's file tree as indexed by kb-core-ui."
GET_STATS_DESC = "Get repo-wide counts: files, symbols, edges, and a per-language breakdown."
MEMORY_SEARCH_DESC = (
    "Semantically search kb-core-ui's vector memory for the codebase RULES, LESSONS, "
    "business-logic notes, and overviews most relevant to a task. Call this before making "
    "changes to learn the project's primary rules and past lessons — it holds knowledge that "
    "is NOT in the code itself."
)
MEMORY_ADD_DESC = (
    "Store a new lesson, rule, business-logic note, or overview in kb-core-ui's vector memory "
    "so it can be recalled later. Use this to persist something important learned during a "
    "task (e.g. a non-obvious rule, a bug's root cause) for future sessions."
)


def _marshal_list(items: list) -> list | None:
    """MCP marshals the store's slices directly, and an empty Go slice built
    by append is nil, which encodes as `null`. The REST layer wraps the same
    calls in nonNil() to force `[]`; internal/mcp deliberately does not, so
    the two surfaces disagree on the empty case by design.
    """
    return [i.to_json_dict() for i in items] if items else None


class Server:
    """Backed by the code graph `store` (resolving file-slice reads against
    `repo_root`) and, when `memory` is not None, the vector memory — letting
    an agent pull relevant codebase rules/lessons in the same session it
    navigates the graph."""

    def __init__(self, store: Store, repo_root: str, memory: MemoryStore | None = None):
        self.store = store
        self.repo_root = repo_root
        self.memory = memory
        self.registry = Registry()
        self._register()

    def _register(self) -> None:
        add = self.registry.add

        add(Tool(
            name="search_symbol",
            description=SEARCH_SYMBOL_DESC,
            params=(
                Param("query", "string",
                      "Substring to match against symbol names, case-insensitive", required=True),
                Param("kind", "string",
                      "Optional filter: module, package, class, interface, function, method, "
                      "const, variable"),
            ),
            handler=self._search_symbol,
        ))
        add(Tool(
            name="get_symbol",
            description=GET_SYMBOL_DESC,
            params=(
                Param("id", "string",
                      "Symbol id, e.g. from search_symbol or get_file_symbols", required=True),
            ),
            handler=self._get_symbol,
        ))
        add(Tool(
            name="get_file_symbols",
            description=GET_FILE_SYMBOLS_DESC,
            params=(Param("path", "string", "Repo-relative file path", required=True),),
            handler=self._get_file_symbols,
        ))
        add(Tool(
            name="get_callees",
            description=GET_CALLEES_DESC,
            params=(Param("id", "string", "Symbol id", required=True),),
            handler=self._get_callees,
        ))
        add(Tool(
            name="get_callers",
            description=GET_CALLERS_DESC,
            params=(Param("id", "string", "Symbol id", required=True),),
            handler=self._get_callers,
        ))
        add(Tool(
            name="get_file_slice",
            description=GET_FILE_SLICE_DESC,
            params=(
                Param("file", "string", "Repo-relative file path", required=True),
                Param("start", "number", "1-indexed start line, inclusive", required=True),
                Param("end", "number", "1-indexed end line, inclusive", required=True),
            ),
            handler=self._get_file_slice,
        ))
        add(Tool(name="get_tree", description=GET_TREE_DESC, handler=self._get_tree))
        add(Tool(name="get_stats", description=GET_STATS_DESC, handler=self._get_stats))

        if self.memory is not None:
            add(Tool(
                name="memory_search",
                description=MEMORY_SEARCH_DESC,
                params=(
                    Param("query", "string",
                          "What you want relevant rules/lessons about, in natural language",
                          required=True),
                    Param("kind", "string",
                          "Optional filter: rule, lesson, business, overview, reference"),
                ),
                handler=self._memory_search,
            ))
            add(Tool(
                name="memory_add",
                description=MEMORY_ADD_DESC,
                params=(
                    Param("kind", "string",
                          "rule, lesson, business, overview, or reference", required=True),
                    Param("title", "string", "Short title", required=True),
                    Param("text", "string", "The knowledge to remember", required=True),
                    Param("source", "string", "Where it came from (optional)"),
                ),
                handler=self._memory_add,
            ))

    # ---- JSON-RPC surface ----------------------------------------------

    def handlers(self) -> dict:
        return {
            "initialize": self._initialize,
            "notifications/initialized": lambda params: None,
            "ping": lambda params: {},
            "tools/list": lambda params: self.registry.listing(),
            "tools/call": self._call_tool,
        }

    def _initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        tool = self.registry.lookup(name) if isinstance(name, str) else None
        if tool is None:
            raise JsonRpcError(METHOD_NOT_FOUND, f"tool not found: {name}")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        return tool.handler(arguments).to_json_dict()

    # ---- graph tools ---------------------------------------------------

    def _search_symbol(self, args: dict) -> ToolResult:
        try:
            results = self.store.search(parse_string(args, "query"), parse_string(args, "kind"))
        except KbError as exc:
            return error_from_exc("search failed", exc)
        return json_result(_marshal_list(results))

    def _get_symbol(self, args: dict) -> ToolResult:
        symbol_id = parse_string(args, "id")
        try:
            sym = self.store.symbol(symbol_id)
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        if sym is None:
            return error_result(f'no symbol with id "{symbol_id}"')
        return json_result(sym.to_json_dict())

    def _get_file_symbols(self, args: dict) -> ToolResult:
        try:
            syms = self.store.symbols_in_file(parse_string(args, "path"))
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        return json_result(_marshal_list(syms))

    def _get_callees(self, args: dict) -> ToolResult:
        try:
            calls = self.store.calls(parse_string(args, "id"))
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        return json_result(_marshal_list(calls))

    def _get_callers(self, args: dict) -> ToolResult:
        try:
            callers = self.store.callers(parse_string(args, "id"))
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        return json_result(_marshal_list(callers))

    def _get_file_slice(self, args: dict) -> ToolResult:
        file = parse_string(args, "file")
        start = parse_int(args, "start", 1)
        end = parse_int(args, "end", start)
        if start < 1 or end < start:
            return error_result("invalid start/end line range")

        # filepath.Join concatenates then cleans, so an absolute or ../-laden
        # path still resolves against the repo root before the check.
        full = os.path.normpath(self.repo_root + os.sep + file.replace("/", os.sep))
        if not full.startswith(os.path.normpath(self.repo_root) + os.sep):
            return error_result("file path escapes repo root")
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            # os.ReadFile fails with an *os.PathError, whose text Python does
            # not reproduce on its own.
            return error_result(f"read failed: {os_error_text('open', full, exc)}")

        all_lines = data.decode("utf-8", errors="replace").split("\n")
        if start > len(all_lines):
            return text_result("")
        if end > len(all_lines):
            end = len(all_lines)
        return text_result("\n".join(all_lines[start - 1 : end]))

    def _get_tree(self, args: dict) -> ToolResult:
        try:
            tree = self.store.tree()
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        return json_result(tree.to_json_dict())

    def _get_stats(self, args: dict) -> ToolResult:
        try:
            stats = self.store.stats()
        except KbError as exc:
            return error_from_exc("lookup failed", exc)
        # store.Stats carries no json tags, so encoding/json falls back to the
        # Go field names — capitalized, in declaration order. The REST
        # /api/stats handler builds its own lowercase map instead, so the two
        # surfaces genuinely differ here.
        return json_result(
            {
                "Files": stats.files,
                "Symbols": stats.symbols,
                "Edges": stats.edges,
                "Languages": stats.languages,
            }
        )

    # ---- memory tools --------------------------------------------------

    def _memory_search(self, args: dict) -> ToolResult:
        try:
            hits = self.memory.search(parse_string(args, "query"), parse_string(args, "kind"), 5)
        except KbError as exc:
            return error_from_exc("memory search failed", exc)
        return json_result(_marshal_list(hits))

    def _memory_add(self, args: dict) -> ToolResult:
        kind = parse_string(args, "kind")
        title = parse_string(args, "title")
        text = parse_string(args, "text")
        source = parse_string(args, "source")
        # Unlike the REST route, an empty kind is invalid here too: the Go
        # switch has no empty case.
        if kind not in VALID_KINDS:
            return error_result("invalid kind (want: rule, lesson, business, overview, reference)")
        try:
            entry = self.memory.add(kind, title, text, source, memory_now())
        except KbError as exc:
            return error_from_exc("memory add failed", exc)
        return json_result(entry.to_json_dict())
