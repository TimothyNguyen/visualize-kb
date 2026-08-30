from __future__ import annotations

import json
import shutil
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from harness.engines import ResolvedEngine, render_argv
from harness.errors import EngineError
from harness.manifest import Fixture
from harness.mcp_client import McpSession, start_mcp_process
from harness.ports import allocate_free_port


@dataclass
class RunContext:
    run_id: str
    engine_name: str
    root: Path
    fixture_root: Path
    db_path: Path
    work_dir: Path
    port: int | None = None


@dataclass(frozen=True)
class CliResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float


@dataclass(frozen=True)
class RestResult:
    status: int
    json_body: Any | None
    text_body: str
    headers: dict[str, str] = field(default_factory=dict)


def _make_writable(path: Path) -> None:
    for p in path.rglob("*"):
        try:
            p.chmod(p.stat().st_mode | stat.S_IWRITE)
        except OSError:
            pass


class RestSession:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def _request(self, url: str, method: str, data: bytes | None = None, headers: dict | None = None) -> RestResult:
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        # Windows can reset an otherwise healthy Go listener while it handles
        # a malformed/unknown route. Retry only requests with no side effects;
        # replaying a real POST could duplicate a memory write.
        retryable = method in {"GET", "HEAD"} or (method == "POST" and data in {b"", b"{}"})
        for attempt in range(2 if retryable else 1):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read()
                    status = resp.status
                    headers = dict(resp.headers.items())
                break
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                status = exc.code
                headers = dict(exc.headers.items())
                break
            except ConnectionResetError:
                if attempt == 0 and retryable:
                    time.sleep(0.05)
                    continue
                raise EngineError(f"REST {method} {url} connection reset")
        # Static assets are not text; decode leniently so a binary body still
        # yields a comparable length without corrupting the JSON paths.
        body = raw.decode("utf-8", errors="replace")
        json_body = None
        if body:
            try:
                json_body = json.loads(body)
            except json.JSONDecodeError:
                json_body = None
        return RestResult(
            status=status,
            json_body=json_body,
            text_body=body,
            headers={k.lower(): v for k, v in headers.items()},
        )

    def get(self, route: str, params: dict[str, str] | None = None) -> RestResult:
        url = self.base_url + route
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._request(url, "GET")

    def post(self, route: str, json_body: Any) -> RestResult:
        data = json.dumps(json_body).encode("utf-8")
        return self._request(self.base_url + route, "POST", data=data, headers={"Content-Type": "application/json"})

    def post_raw(self, route: str, body_text: str) -> RestResult:
        """Sends body_text verbatim, so a manifest can exercise malformed-JSON
        error paths that post() would json-encode away."""
        return self._request(
            self.base_url + route,
            "POST",
            data=body_text.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def delete(self, route: str) -> RestResult:
        return self._request(self.base_url + route, "DELETE")


class ProcessRunner:
    def __init__(self, engine: ResolvedEngine, work_root: Path, *, timeout_s: float = 30.0):
        self.engine = engine
        # Must be absolute: run_cli/rest_session/mcp_session set the child
        # process's cwd to ctx.fixture_root, and also pass ctx.fixture_root
        # (and ctx.db_path) as CLI args. A relative work_root would make the
        # engine binary re-resolve that same relative path against its new
        # cwd (already inside fixture_root), doubling the path.
        self.work_root = Path(work_root).resolve()
        self.timeout_s = timeout_s

    def prepare_run(self, fixture: Fixture, run_label: str) -> RunContext:
        run_id = uuid.uuid4().hex[:8]
        root = self.work_root / f"{run_label}-{run_id}"
        fixture_root = root / "repo"
        db_path = root / "db" / "graph.db"
        work_dir = root / "work"

        shutil.copytree(fixture.repo_dir, fixture_root)
        _make_writable(fixture_root)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)

        return RunContext(
            run_id=run_id,
            engine_name=self.engine.config.name,
            root=root,
            fixture_root=fixture_root,
            db_path=db_path,
            work_dir=work_dir,
        )

    # A fixed, committed stand-in for web/dist; see tests/webdir/README.md.
    WEB_DIR = Path(__file__).resolve().parents[1] / "tests" / "webdir"

    def _base_values(self, ctx: RunContext) -> dict[str, str]:
        return {
            "bin": self.engine.bin_path,
            "repo": str(ctx.fixture_root),
            "db": str(ctx.db_path),
            "web_dir": str(self.WEB_DIR),
        }

    def run_cli(self, ctx: RunContext, command: str, values: dict[str, str]) -> CliResult:
        template = self.engine.config.cli_templates.get(command)
        if template is None:
            raise EngineError(
                f"engine {self.engine.config.name!r} has no cli template for command {command!r}"
            )
        merged = {**self._base_values(ctx), **values}
        argv = render_argv(template, merged)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=ctx.fixture_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"cli command {command!r} timed out after {self.timeout_s}s: {argv}") from exc
        duration = time.monotonic() - start
        return CliResult(
            argv=argv, exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, duration_s=duration
        )

    @contextmanager
    def rest_session(self, ctx: RunContext, values: dict[str, str]) -> Iterator[RestSession]:
        config = self.engine.config
        if config.serve_template is None:
            raise EngineError(f"engine {config.name!r} has no serve_template")
        if ctx.port is None:
            ctx.port = allocate_free_port()
        merged = {**self._base_values(ctx), "port": str(ctx.port), **values}
        argv = render_argv(config.serve_template, merged)
        proc = subprocess.Popen(
            argv,
            cwd=ctx.fixture_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        base_url = f"http://127.0.0.1:{ctx.port}"
        try:
            deadline = time.monotonic() + config.startup_timeout_s
            last_err: Exception | None = None
            ready = False
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    out, err = proc.communicate()
                    raise EngineError(f"serve process exited early (code {proc.returncode}): {err or out}")
                try:
                    with urllib.request.urlopen(base_url + config.ready_probe, timeout=1) as resp:
                        if resp.status == 200:
                            ready = True
                            break
                except (urllib.error.URLError, ConnectionError) as exc:
                    last_err = exc
                    time.sleep(0.1)
            if not ready:
                raise EngineError(
                    f"serve process did not become ready within {config.startup_timeout_s}s: {last_err}"
                )
            yield RestSession(base_url)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    @contextmanager
    def mcp_session(self, ctx: RunContext, values: dict[str, str]) -> Iterator[McpSession]:
        config = self.engine.config
        if config.mcp_template is None:
            raise EngineError(f"engine {config.name!r} has no mcp_template")
        merged = {**self._base_values(ctx), **values}
        argv = render_argv(config.mcp_template, merged)
        session = start_mcp_process(argv, cwd=ctx.fixture_root)
        try:
            session.initialize()
            yield session
        finally:
            session.close()

    def cleanup(self, ctx: RunContext) -> None:
        shutil.rmtree(ctx.root, ignore_errors=True)
