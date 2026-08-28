from __future__ import annotations

from typing import Any

from harness.engines import ResolvedEngine
from harness.errors import EngineError
from harness.manifest import Operation
from harness.mcp_client import McpSession
from harness.runner import ProcessRunner, RestSession, RunContext


class SessionPool:
    """Lazily starts at most one RestSession and one McpSession per
    RunContext, reused across all operations in the same fixture run."""

    def __init__(self, runner: ProcessRunner, ctx: RunContext):
        self.runner = runner
        self.ctx = ctx
        self._rest_cm = None
        self._rest: RestSession | None = None
        self._mcp_cm = None
        self._mcp: McpSession | None = None

    def rest(self) -> RestSession:
        if self._rest is None:
            self._rest_cm = self.runner.rest_session(self.ctx, {})
            self._rest = self._rest_cm.__enter__()
        return self._rest

    def mcp(self) -> McpSession:
        if self._mcp is None:
            self._mcp_cm = self.runner.mcp_session(self.ctx, {})
            self._mcp = self._mcp_cm.__enter__()
        return self._mcp

    def close(self) -> None:
        if self._mcp_cm is not None:
            self._mcp_cm.__exit__(None, None, None)
            self._mcp_cm = None
            self._mcp = None
        if self._rest_cm is not None:
            self._rest_cm.__exit__(None, None, None)
            self._rest_cm = None
            self._rest = None

    def __enter__(self) -> "SessionPool":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def execute_operation(
    runner: ProcessRunner,
    ctx: RunContext,
    op: Operation,
    engine: ResolvedEngine,
    sessions: SessionPool,
) -> Any:
    for setup_op in op.setup:
        execute_operation(runner, ctx, setup_op, engine, sessions)

    if op.kind == "cli":
        return runner.run_cli(ctx, op.command, op.args)

    if op.kind == "rest":
        rest = sessions.rest()
        method = (op.method or "GET").upper()
        if method == "GET":
            return rest.get(op.route, op.params or None)
        if method == "POST":
            return rest.post(op.route, op.params)
        if method == "DELETE":
            return rest.delete(op.route)
        raise EngineError(f"unsupported rest method {op.method!r} for operation {op.id!r}")

    if op.kind == "mcp":
        mcp = sessions.mcp()
        return mcp.call_tool(op.tool, op.params)

    if op.kind == "fs":
        target = ctx.fixture_root / op.path
        if op.fs_op == "replace":
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace(op.find, op.replace, 1), encoding="utf-8")
        elif op.fs_op == "delete":
            target.unlink(missing_ok=True)
        else:
            raise EngineError(f"unsupported fs_op {op.fs_op!r} for operation {op.id!r}")
        return None

    raise EngineError(f"unsupported operation kind {op.kind!r} for operation {op.id!r}")
