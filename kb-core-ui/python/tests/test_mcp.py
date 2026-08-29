"""Port of internal/mcp/server_test.go, plus coverage for the JSON-RPC
transport the Go tests get from mcp-go's in-process client.

Requests go through the handler map rather than a pipe, except in the
serve_stdio tests, which drive the real newline-delimited framing.
"""

from __future__ import annotations

import io
import json

import pytest

from kb_core_ui import jsonx
from kb_core_ui.indexer import index
from kb_core_ui.mcp import Server, serve_stdio
from kb_core_ui.mcp.protocol import METHOD_NOT_FOUND, PARSE_ERROR, PROTOCOL_VERSION
from kb_core_ui.memory import HashingEmbedder
from kb_core_ui.memory import Store as MemoryStore
from kb_core_ui.store import Store


def call_tool(app: Server, name: str, arguments: dict | None = None) -> dict:
    """Returns the raw tools/call result, isError included."""
    return app.handlers()["tools/call"]({"name": name, "arguments": arguments or {}})


def tool_text(app: Server, name: str, arguments: dict | None = None) -> str:
    result = call_tool(app, name, arguments)
    assert not result.get("isError"), result
    return result["content"][0]["text"]


def tool_json(app: Server, name: str, arguments: dict | None = None):
    return json.loads(tool_text(app, name, arguments))


@pytest.fixture
def app(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.go").write_text(
        "package main\n\n// Add sums two ints.\nfunc Add(a int, b int) int {\n\treturn helper(a, b)\n}\n",
        encoding="utf-8",
    )
    (repo / "b.go").write_text(
        "package main\n\nfunc helper(a int, b int) int {\n\treturn a + b\n}\n",
        encoding="utf-8",
    )
    with Store(str(tmp_path / "graph.db")) as store:
        index(str(repo), store)
        yield Server(store, str(repo), None)


@pytest.fixture
def memory_app(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with Store(str(tmp_path / "graph.db")) as store:
        with MemoryStore(str(tmp_path / "memory.db"), HashingEmbedder(512)) as mem:
            yield Server(store, str(repo), mem)


def test_tools_end_to_end(app):
    results = tool_json(app, "search_symbol", {"query": "Add"})
    assert [r["name"] for r in results] == ["Add"]
    add_id = results[0]["id"]

    sym = tool_json(app, "get_symbol", {"id": add_id})
    assert sym["doc"]
    assert len(sym["params"]) == 2

    file_syms = tool_json(app, "get_file_symbols", {"path": "a.go"})
    assert len(file_syms) == 1

    callees = tool_json(app, "get_callees", {"id": add_id})
    assert len(callees) == 1
    # Lowercase per the json tags; a struct without them would capitalize.
    assert set(callees[0]) == {"edge", "symbol"}
    helper_id = callees[0]["symbol"]["id"]

    callers = tool_json(app, "get_callers", {"id": helper_id})
    assert len(callers) == 1

    assert tool_text(app, "get_file_slice", {"file": "a.go", "start": 4, "end": 6})
    assert tool_json(app, "get_tree")["type"] == "dir"

    stats = tool_json(app, "get_stats")
    # store.Stats has no json tags, so the Go field names survive marshalling.
    assert stats["Files"] == 2
    assert stats["Symbols"] == 2


def test_empty_results_marshal_as_null(app):
    """internal/mcp marshals the store's slices directly, so an empty result
    is a nil Go slice and encodes as null — unlike the REST layer, which
    wraps the same calls in nonNil()."""
    assert tool_json(app, "search_symbol", {"query": "zzzznope"}) is None
    assert tool_json(app, "get_file_symbols", {"path": "nope.go"}) is None
    assert tool_json(app, "get_callees", {"id": "nope"}) is None
    assert tool_json(app, "get_callers", {"id": "nope"}) is None


def test_get_symbol_not_found(app):
    result = call_tool(app, "get_symbol", {"id": "nope"})
    assert result["isError"] is True
    assert result["content"][0]["text"] == 'no symbol with id "nope"'


def test_file_slice_guards(app):
    bad_range = call_tool(app, "get_file_slice", {"file": "a.go", "start": 5, "end": 1})
    assert bad_range["isError"] is True
    assert bad_range["content"][0]["text"] == "invalid start/end line range"

    escape = call_tool(app, "get_file_slice", {"file": "../../etc/passwd", "start": 1, "end": 2})
    assert escape["isError"] is True
    assert escape["content"][0]["text"] == "file path escapes repo root"

    missing = call_tool(app, "get_file_slice", {"file": "nope.go", "start": 1, "end": 2})
    assert missing["isError"] is True
    # os.ReadFile fails with an *os.PathError: "open <path>: <platform text>".
    assert missing["content"][0]["text"].startswith("read failed: open ")

    # Past EOF is empty text, not an error.
    past_eof = call_tool(app, "get_file_slice", {"file": "a.go", "start": 9998, "end": 9999})
    assert "isError" not in past_eof
    assert past_eof["content"][0]["text"] == ""


def test_memory_tools(memory_app):
    added = tool_text(
        memory_app,
        "memory_add",
        {
            "kind": "rule",
            "title": "Edge resolution",
            "text": "Call edges resolve by receiver type within the same package; "
            "never across language families.",
        },
    )
    assert "Edge resolution" in added

    hits = tool_json(
        memory_app,
        "memory_search",
        {"query": "how do call edges get resolved between packages"},
    )
    assert hits and hits[0]["entry"]["title"] == "Edge resolution"

    invalid = call_tool(memory_app, "memory_add", {"kind": "bogus", "title": "x", "text": "y"})
    assert invalid["isError"] is True
    assert invalid["content"][0]["text"] == (
        "invalid kind (want: rule, lesson, business, overview, reference)"
    )

    # Unlike the REST filter, an empty kind is not a valid entry kind here:
    # the Go switch has no empty case.
    empty_kind = call_tool(memory_app, "memory_add", {"kind": "", "title": "x", "text": "y"})
    assert empty_kind["isError"] is True


def test_memory_tools_absent_without_a_store(app):
    names = [t["name"] for t in app.registry.listing()["tools"]]
    assert "memory_search" not in names
    assert "memory_add" not in names


def test_tools_list_shape(memory_app):
    listing = memory_app.registry.listing()
    names = [t["name"] for t in listing["tools"]]
    # mcp-go serves tools/list sorted by name, not in registration order.
    assert names == sorted(names)
    assert len(names) == 10

    by_name = {t["name"]: t for t in listing["tools"]}
    slice_tool = by_name["get_file_slice"]
    assert slice_tool["inputSchema"]["type"] == "object"
    # Required order follows declaration, not the sorted properties.
    assert slice_tool["inputSchema"]["required"] == ["file", "start", "end"]
    assert slice_tool["inputSchema"]["properties"]["start"]["type"] == "number"
    assert slice_tool["annotations"] == {
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
        "readOnlyHint": False,
    }

    # A tool with no parameters still carries an empty object schema.
    assert by_name["get_tree"]["inputSchema"] == {
        "properties": {},
        "required": [],
        "type": "object",
    }


def test_initialize_reports_the_protocol_version(app):
    result = app.handlers()["initialize"]({})
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"] == {"name": "kb-core-ui", "version": "0.1.0"}


def _serve(app: Server, messages: list[dict]) -> list[dict]:
    stdin = io.StringIO("".join(jsonx.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    serve_stdio(app.handlers(), stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line]


def test_stdio_framing_is_one_message_per_line(app):
    replies = _serve(
        app,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ],
    )
    # The notification gets no reply, so two requests produce exactly two lines.
    assert [r["id"] for r in replies] == [1, 2]
    assert replies[1]["result"]["tools"]


def test_stdio_reports_protocol_errors(app):
    stdin = io.StringIO('not json\n{"jsonrpc":"2.0","id":7,"method":"nope","params":{}}\n')
    stdout = io.StringIO()
    serve_stdio(app.handlers(), stdin=stdin, stdout=stdout)
    replies = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
    assert replies[0]["error"]["code"] == PARSE_ERROR
    assert replies[1]["id"] == 7
    assert replies[1]["error"]["code"] == METHOD_NOT_FOUND


def test_unknown_tool_is_a_jsonrpc_error(app):
    replies = _serve(
        app,
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "no_such_tool", "arguments": {}}}],
    )
    assert replies[0]["error"]["code"] == METHOD_NOT_FOUND
