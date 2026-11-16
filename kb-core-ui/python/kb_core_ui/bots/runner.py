"""Executes bots by re-invoking the kb-core-ui entrypoint and tracks their
runs in memory — the Python side of internal/bots/runner.go.

Runs are not persisted: this is a local dev tool, and restarting clears the
history.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field

from kb_core_ui.bots.registry import Def, lookup
from kb_core_ui.gotime import GoTime, now


@dataclass
class Run:
    id: str = ""
    bot: str = ""
    status: str = "running"  # "running" | "succeeded" | "failed"
    started_at: GoTime = field(default_factory=lambda: GoTime(0))
    finished_at: GoTime | None = None
    exit_code: int | None = None
    output: str = ""

    def to_json_dict(self) -> dict:
        out: dict = {
            "id": self.id,
            "bot": self.bot,
            "status": self.status,
            "startedAt": self.started_at.format(),
        }
        if self.finished_at is not None:
            out["finishedAt"] = self.finished_at.format()
        if self.exit_code is not None:
            out["exitCode"] = self.exit_code
        out["output"] = self.output
        return out

    def summary_json_dict(self) -> dict:
        out = self.to_json_dict()
        out.pop("output")
        return out


# Kept as a distinct name so the REST layer can keep mirroring Go's two
# structs, even though the summary is just a Run without its output.
RunSummary = Run


class UnknownBotError(Exception):
    def __init__(self, name: str):
        super().__init__("unknown bot: " + name)
        self.name = name


class MissingArgError(Exception):
    def __init__(self, arg: str):
        super().__init__("missing required arg: " + arg)
        self.arg = arg


def is_truthy(s: str) -> bool:
    return s in ("true", "1", "yes", "on")


def build_args(definition: Def, args: dict[str, str], repo_root: str) -> list[str]:
    """Turns a bot def + user args into the argv after `kb-core-ui bot`.
    Positional args come first in declaration order; the rest become flags,
    booleans as a bare "--name" when truthy. Arg names use underscores
    (JSON-friendly) while CLI flags use dashes, so "dry_run" -> "--dry-run".
    """
    by_name = {a.name: a for a in definition.args}

    out = ["bot", definition.subcommand]
    for name in definition.positional:
        # May be empty for optional positionals; Go passes the empty string.
        out.append(args.get(name, ""))

    # Deterministic flag order for testability.
    flag_names = sorted(
        a.name
        for a in definition.args
        if a.name not in definition.positional and args.get(a.name, "")
    )
    for name in flag_names:
        flag = "--" + name.replace("_", "-")
        if by_name[name].is_bool:
            if is_truthy(args[name]):
                out.append(flag)
            continue
        out += [flag, args[name]]
    out += ["--repo", repo_root]
    return out


class Runner:
    """Safe for concurrent use. self_argv is the command prefix that runs this
    same program (`<self_argv> bot <sub> ...`)."""

    def __init__(self, self_argv: list[str] | str, repo_root: str):
        self.self_argv = [self_argv] if isinstance(self_argv, str) else list(self_argv)
        self.repo_root = repo_root
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        self._seq = 0
        self.now = now

    def start(self, bot_name: str, args: dict[str, str] | None) -> Run:
        """Validates args, launches the bot in the background, and returns the
        initial (running) Run. Callers poll get() to observe progress."""
        definition = lookup(bot_name)
        if definition is None:
            raise UnknownBotError(bot_name)
        args = args or {}
        for a in definition.args:
            if a.required and not args.get(a.name, ""):
                raise MissingArgError(a.name)

        cmd_args = build_args(definition, args, self.repo_root)

        with self._lock:
            self._seq += 1
            run = Run(id=f"run-{self._seq}", bot=bot_name, status="running",
                      started_at=self.now())
            self._runs[run.id] = run
            snapshot = _copy(run)

        threading.Thread(target=self._execute, args=(run, cmd_args), daemon=True).start()
        return snapshot

    def _execute(self, run: Run, cmd_args: list[str]) -> None:
        chunks: list[str] = []
        try:
            proc = subprocess.Popen(
                self.self_argv + cmd_args,
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            with self._lock:
                run.output = f"\n[runner] failed to execute bot: {exc}\n"
                run.exit_code = -1
                run.finished_at = self.now()
                run.status = "failed"
            return

        assert proc.stdout is not None
        # Stream output into the Run as it is produced, so a polling reader
        # sees progress rather than only the final blob.
        for line in proc.stdout:
            chunks.append(line)
            with self._lock:
                run.output = "".join(chunks)
        exit_code = proc.wait()

        with self._lock:
            run.output = "".join(chunks)
            run.exit_code = exit_code
            run.finished_at = self.now()
            run.status = "succeeded" if exit_code == 0 else "failed"

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            run = self._runs.get(run_id)
            return None if run is None else _copy(run)

    def list(self) -> list[Run]:
        with self._lock:
            runs = [_copy(r) for r in self._runs.values()]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs


def _copy(run: Run) -> Run:
    return Run(
        id=run.id,
        bot=run.bot,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        exit_code=run.exit_code,
        output=run.output,
    )
