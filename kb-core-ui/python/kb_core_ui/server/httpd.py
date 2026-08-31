"""Binds the Server to a real socket — the equivalent of Go's
http.ListenAndServe(addr, srv).

ThreadingHTTPServer matches net/http's goroutine-per-connection model, which
matters because the bot endpoints start work that outlives the request and
the dashboard polls run status while it runs.
"""

from __future__ import annotations

import sys
import threading
import traceback
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kb_core_ui.server.app import Server
from kb_core_ui.server.wire import Request, Response


class _Handler(BaseHTTPRequestHandler):
    # net/http speaks HTTP/1.1 with keep-alive; the default here is 1.0,
    # which closes every connection and makes the harness reconnect per call.
    protocol_version = "HTTP/1.1"
    server_version = "kb-core-ui"
    sys_version = ""

    @property
    def _app(self) -> Server:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        # net/http logs nothing per request; neither should the port.
        return

    def _dispatch(self) -> None:
        raw_path, _, query_string = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b""

        try:
            decoded_path = urllib.parse.unquote(raw_path, errors="surrogateescape")
        except UnicodeDecodeError:
            decoded_path = raw_path

        req = Request(
            method=self.command,
            raw_path=raw_path,
            path=decoded_path,
            query=urllib.parse.parse_qs(query_string, keep_blank_values=True),
            query_string=query_string,
            body=body,
        )
        try:
            resp = self._app.serve(req)
        except Exception:  # noqa: BLE001 - net/http recovers a panicking handler
            # net/http logs the panic and its stack, then closes the
            # connection with no body. Swallowing it silently would turn a
            # handler bug into an unexplained 500 during parity runs.
            traceback.print_exc(file=sys.stderr)
            resp = Response(status=500, body=b"", headers={})
        if resp.stream is not None:
            self._write_stream(resp, include_body=self.command != "HEAD")
        else:
            self._write(resp, include_body=self.command != "HEAD")

    def _write(self, resp: Response, include_body: bool = True) -> None:
        self.send_response(resp.status)
        for name, value in resp.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        if include_body and resp.body:
            self.wfile.write(resp.body)

    def _write_stream(self, resp: Response, include_body: bool = True) -> None:
        """Writes an SSE (or any other) streaming Response. No Content-Length
        is known up front, so the connection is closed at the end of the
        stream instead of trying to keep it alive for a following request --
        matching net/http's own behavior for a handler that never sets one.
        """

        self.send_response(resp.status)
        for name, value in resp.headers.items():
            if name.lower() != "content-length":
                self.send_header(name, value)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if not include_body:
            return
        iterator = resp.stream()
        try:
            for chunk in iterator:
                if not chunk:
                    continue
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The client disconnected mid-stream (tab closed, abort()
            # called, network drop). This is expected and not a server
            # error -- propagate cancellation into the generator so any
            # workflow/provider work it still owns unwinds and its
            # try/finally cleanup runs, then stop writing silently instead
            # of turning a normal disconnect into a logged crash.
            close = getattr(iterator, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 - best-effort cleanup only
                    pass

    do_GET = _dispatch
    do_HEAD = _dispatch
    do_POST = _dispatch
    do_DELETE = _dispatch
    do_OPTIONS = _dispatch
    do_PUT = _dispatch
    do_PATCH = _dispatch


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], app: Server):
        self.app = app
        super().__init__(addr, _Handler)


def listen_and_serve(
    host: str,
    port: int,
    app: Server,
    *,
    stop_event: threading.Event | None = None,
    ready: Callable[[int], None] | None = None,
) -> None:
    """Serve until process exit or an optional harness stop signal.

    ``port=0`` plus ``ready`` lets integration tests use an OS-assigned port
    without a bind race. Production callers keep the original blocking
    three-argument behavior.
    """
    httpd = _HTTPServer((host, port), app)
    if ready is not None:
        ready(int(httpd.server_address[1]))
    try:
        if stop_event is None:
            httpd.serve_forever()
        else:
            httpd.timeout = 0.1
            while not stop_event.is_set():
                httpd.handle_request()
    finally:
        httpd.server_close()
