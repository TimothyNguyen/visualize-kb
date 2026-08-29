"""Port of internal/server/server_test.go, memory_test.go and bots_test.go.

Requests go through Server.serve rather than a socket, so the tests exercise
the mux and the handlers without a listener. The transport itself
(httpd.py) is covered end to end by the harness, which drives a real
`kb-core-ui serve` process for every REST parity case.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse

import pytest

from kb_core_ui.bots import Runner
from kb_core_ui.indexer import index
from kb_core_ui.memory import HashingEmbedder
from kb_core_ui.memory import Store as MemoryStore
from kb_core_ui.server import Server
from kb_core_ui.server.wire import Request
from kb_core_ui.store import Store


def request(app: Server, method: str, target: str, body: bytes = b"") -> tuple[int, object, str]:
    """Returns (status, decoded JSON or None, raw text)."""
    raw_path, _, query_string = target.partition("?")
    req = Request(
        method=method,
        raw_path=raw_path,
        path=urllib.parse.unquote(raw_path),
        query=urllib.parse.parse_qs(query_string, keep_blank_values=True),
        query_string=query_string,
        body=body,
    )
    resp = app.serve(req)
    text = resp.body.decode("utf-8", errors="replace")
    try:
        decoded = json.loads(text)
    except ValueError:
        decoded = None
    return resp.status, decoded, text


@pytest.fixture
def graph_app(tmp_path):
    # Nested under pkg/ so symbol ids (filePath + ":" + name) contain a "/" —
    # needed to exercise the %2F-in-id routing path.
    pkg = tmp_path / "repo" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "a.go").write_text(
        "package main\n\n// Add sums two ints.\nfunc Add(a int, b int) int {\n\treturn helper(a, b)\n}\n",
        encoding="utf-8",
    )
    (pkg / "b.go").write_text(
        "package main\n\nfunc helper(a int, b int) int {\n\treturn a + b\n}\n",
        encoding="utf-8",
    )
    with Store(str(tmp_path / "graph.db")) as store:
        index(str(tmp_path / "repo"), store)
        yield Server(store, str(tmp_path / "repo"), "", None, None)


@pytest.fixture
def memory_app(tmp_path):
    with Store(str(tmp_path / "graph.db")) as store:
        with MemoryStore(str(tmp_path / "memory.db"), HashingEmbedder(512)) as mem:
            yield Server(store, str(tmp_path), "", None, mem)


@pytest.fixture
def bots_app(tmp_path):
    with Store(str(tmp_path / "graph.db")) as store:
        # A stand-in for the kb-core-ui entrypoint that just echoes and exits 0.
        fake = tmp_path / "fake_entrypoint.py"
        fake.write_text("import sys\nprint('ran:', ' '.join(sys.argv[1:]))\n", encoding="utf-8")
        runner = Runner([sys.executable, str(fake)], str(tmp_path))
        yield Server(store, str(tmp_path), "", runner, None)


def test_graph_endpoints(graph_app):
    status, tree, _ = request(graph_app, "GET", "/api/tree")
    assert status == 200
    assert [c["name"] for c in tree["children"]] == ["pkg"]
    assert len(tree["children"][0]["children"]) == 2

    _, stats, _ = request(graph_app, "GET", "/api/stats")
    assert (stats["files"], stats["symbols"], stats["edges"]) == (2, 2, 1)

    _, syms, _ = request(graph_app, "GET", "/api/files/pkg/a.go/symbols")
    assert [s["name"] for s in syms] == ["Add"]
    add_id = syms[0]["id"]

    # The frontend percent-encodes ids with encodeURIComponent before building
    # the URL, so the test must too — otherwise it would miss a routing bug
    # that only bites once %2F is on the wire.
    encoded = urllib.parse.quote(add_id, safe="")
    assert "%" in encoded, f"id {add_id!r} has no separator to encode"

    _, sym, _ = request(graph_app, "GET", "/api/symbols/" + encoded)
    assert sym["name"] == "Add"
    assert sym["doc"]
    assert len(sym["params"]) == 2

    _, calls, _ = request(graph_app, "GET", f"/api/symbols/{encoded}/calls")
    assert len(calls) == 1
    # API_CONTRACT.md types these lowercase.
    assert set(calls[0]) == {"edge", "symbol"}

    _, callers, _ = request(graph_app, "GET", f"/api/symbols/{encoded}/callers")
    assert callers == [], "an empty result must serialize as [] not null"

    _, graph, _ = request(graph_app, "GET", "/api/graph")
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1

    _, sub, _ = request(
        graph_app, "GET", "/api/graph/subgraph?symbol=" + urllib.parse.quote(add_id) + "&depth=2"
    )
    assert sub["center"] == add_id

    _, results, _ = request(graph_app, "GET", "/api/search?q=Add")
    assert [r["id"] for r in results] == [add_id]

    _, src, _ = request(graph_app, "GET", "/api/source?file=pkg/a.go&start=1&end=3")
    assert len(src["lines"]) == 3

    status, _, _ = request(graph_app, "GET", "/api/symbols/does-not-exist")
    assert status == 404


def test_members_and_unknown_suffix(graph_app):
    status, body, _ = request(graph_app, "GET", "/api/symbols/nope/members")
    assert (status, body) == (200, [])

    # An unrecognized suffix falls through to the mux's NotFound, which is
    # plain text rather than the JSON error envelope.
    status, body, text = request(graph_app, "GET", "/api/symbols/nope/bogus")
    assert status == 404
    assert body is None
    assert text == "404 page not found\n"


def test_source_guards(graph_app):
    status, body, _ = request(graph_app, "GET", "/api/source?file=../../etc/passwd&start=1&end=2")
    assert (status, body["error"]) == (400, "file path escapes repo root")

    status, body, _ = request(graph_app, "GET", "/api/source?file=pkg/a.go&start=x&end=y")
    assert (status, body["error"]) == (400, "invalid start/end")

    # Past EOF is not an error: Go returns an empty slice at the given start.
    status, body, _ = request(graph_app, "GET", "/api/source?file=pkg/a.go&start=9998&end=9999")
    assert (status, body["lines"], body["startLine"]) == (200, [], 9998)


def test_cors_and_preflight(graph_app):
    status, _, _ = request(graph_app, "OPTIONS", "/api/tree")
    assert status == 204

    req = Request(
        method="GET", raw_path="/api/tree", path="/api/tree", query={}, query_string="", body=b""
    )
    resp = graph_app.serve(req)
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_api_only_index(graph_app):
    status, _, text = request(graph_app, "GET", "/")
    assert status == 200
    assert text.startswith("kb-core-ui API server is running.")


def test_memory_endpoints(memory_app):
    body = json.dumps(
        {
            "kind": "rule",
            "title": "Edge resolution",
            "text": "Call edges resolve by receiver type within the same package.",
        }
    ).encode("utf-8")
    status, entry, _ = request(memory_app, "POST", "/api/memory", body)
    assert status == 200
    assert entry["id"] and entry["kind"] == "rule"

    _, listed, _ = request(memory_app, "GET", "/api/memory")
    assert len(listed) == 1

    _, hits, _ = request(
        memory_app, "GET", "/api/memory/search?q=how+are+call+edges+resolved+in+a+package"
    )
    assert hits and hits[0]["entry"]["title"] == "Edge resolution"

    status, _, _ = request(
        memory_app,
        "POST",
        "/api/memory",
        json.dumps({"kind": "nope", "title": "x", "text": "y"}).encode("utf-8"),
    )
    assert status == 400

    status, removed, _ = request(memory_app, "DELETE", "/api/memory/" + entry["id"])
    assert (status, removed) == (200, {"removed": True})

    _, after, _ = request(memory_app, "GET", "/api/memory")
    assert after == []

    status, body, _ = request(memory_app, "DELETE", "/api/memory/" + entry["id"])
    assert (status, body["error"]) == (404, "no memory with id " + entry["id"])


def test_memory_kind_filter_is_validated(memory_app):
    status, body, _ = request(memory_app, "GET", "/api/memory?kind=bogus")
    assert (status, body["error"]) == (400, "invalid kind")

    # An empty kind means "no filter", not an invalid one.
    status, _, _ = request(memory_app, "GET", "/api/memory?kind=")
    assert status == 200


def test_bots_endpoints(bots_app):
    _, defs, _ = request(bots_app, "GET", "/api/bots")
    assert len(defs) >= 2
    assert any(d["name"] == "graph-sync" for d in defs)
    # Every roster entry must carry an array, never null.
    assert all(isinstance(d["args"], list) for d in defs)

    status, run, _ = request(bots_app, "POST", "/api/bots/graph-sync/run", b"{}")
    assert status == 200
    assert run["id"] and run["bot"] == "graph-sync"

    deadline = time.monotonic() + 15
    final = run
    while time.monotonic() < deadline:
        _, final, _ = request(bots_app, "GET", "/api/bots/runs/" + run["id"])
        if final["status"] != "running":
            break
        time.sleep(0.05)
    assert final["status"] == "succeeded", final
    assert final["output"]

    _, summaries, _ = request(bots_app, "GET", "/api/bots/runs")
    assert [s["id"] for s in summaries] == [run["id"]]
    assert "output" not in summaries[0]

    status, body, _ = request(bots_app, "POST", "/api/bots/pr-review/run", b"{}")
    assert status == 400, body

    status, _, _ = request(bots_app, "POST", "/api/bots/nope/run", b"{}")
    assert status == 404

    status, body, _ = request(bots_app, "POST", "/api/bots/graph-sync/bogus", b"{}")
    assert (status, body["error"]) == (404, "not found")


def test_bots_disabled_when_no_runner(graph_app):
    # With no runner the bot patterns are never registered, so the catch-all
    # answers instead — it must not be a 200 JSON roster.
    status, _, _ = request(graph_app, "GET", "/api/bots")
    assert status != 200


def test_memory_disabled_when_no_store(graph_app):
    status, _, _ = request(graph_app, "GET", "/api/memory")
    assert status != 200


@pytest.fixture
def spa_app(tmp_path):
    """A Server with a web_dir, as `serve` builds when web/dist exists."""
    web = tmp_path / "dist"
    (web / "assets").mkdir(parents=True)
    # Written as bytes: the handler serves files verbatim, so a fixture that
    # let Windows translate \n to \r\n would be asserting the wrong thing.
    (web / "index.html").write_bytes(b"<!doctype html><div id=root></div>")
    (web / "assets" / "app.js").write_bytes(b"export const x = 1\n")
    (web / "assets" / "app.css").write_bytes(b".x{color:red}\n")
    (web / "favicon.svg").write_bytes(b"<svg/>")
    with Store(str(tmp_path / "graph.db")) as store:
        yield Server(store, str(tmp_path), str(web), None, None)


def test_spa_serves_static_files(spa_app):
    status, _, text = request(spa_app, "GET", "/assets/app.js")
    assert status == 200
    assert text == "export const x = 1\n"


def test_spa_falls_back_to_index_for_client_routes(spa_app):
    """A client-side route is not a real file, so it must return index.html
    rather than 404 — otherwise a deep link or a refresh breaks the app."""
    index = request(spa_app, "GET", "/")[2]
    assert request(spa_app, "GET", "/symbols/does-not-exist")[2] == index
    assert request(spa_app, "GET", "/memory")[2] == index


def test_spa_does_not_shadow_the_api(spa_app):
    # /api/* patterns are more specific than "/", so they still win.
    status, body, _ = request(spa_app, "GET", "/api/stats")
    assert status == 200
    assert body["files"] == 0


def test_content_types_follow_the_platform_mime_table(spa_app):
    def content_type(path):
        req = Request(
            method="GET", raw_path=path, path=path, query={}, query_string="", body=b""
        )
        return spa_app.serve(req).headers["Content-Type"]

    # Go appends charset=utf-8 to text/* types that lack one, and leaves
    # everything else as the mime table gives it.
    assert content_type("/assets/app.css") == "text/css; charset=utf-8"
    assert content_type("/").startswith("text/html")
    assert content_type("/favicon.svg") == "image/svg+xml"
    js = content_type("/assets/app.js")
    assert js in ("application/javascript", "text/javascript; charset=utf-8")


def test_spa_path_traversal_falls_back_to_index(spa_app):
    """The mux cleans the path before dispatch, so ../ never reaches the file
    read; a cleaned path that is not a real file lands on index.html."""
    index = request(spa_app, "GET", "/")[2]
    status, _, text = request(spa_app, "GET", "/assets/../../../../etc/passwd")
    assert status in (200, 301)
    if status == 200:
        assert text == index
