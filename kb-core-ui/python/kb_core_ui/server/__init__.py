"""The REST API — the Python side of internal/server/.

Split three ways so the parity-critical parts stay isolated: wire.py fixes
the exact response bytes, mux.py reproduces Go 1.22's ServeMux dispatch, and
app.py is a line-for-line port of the handlers.
"""

from kb_core_ui.server.app import Server
from kb_core_ui.server.httpd import listen_and_serve
from kb_core_ui.server.wire import Request, Response

__all__ = ["Server", "listen_and_serve", "Request", "Response"]
