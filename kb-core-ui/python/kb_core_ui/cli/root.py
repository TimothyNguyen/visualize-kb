"""The kb-core-ui command tree.

Every Use/Short/Long string and every flag name, type, default and usage
string here is a copy of the Go original in cmd/kb-core-ui/. They are user
visible through --help and through the usage block printed on any error, so
the cli-surface baselines compare them byte for byte.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from kb_core_ui.cli.command import (
    Command,
    Flag,
    exact_args,
    maximum_n_args,
    no_args,
)
from kb_core_ui.config import (
    default_db_path,
    ensure_db_dir,
    memory_db_path,
    resolve_repo_path,
    workspace_registry_path,
)
from kb_core_ui.bots import Runner as BotRunner
from kb_core_ui.errors import KbError
from kb_core_ui.indexer import index
from kb_core_ui.mcp import Server as McpServer
from kb_core_ui.mcp import serve_stdio
from kb_core_ui.memory import Store as MemoryStore
from kb_core_ui.memory import now as memory_now
from kb_core_ui.rag.config import RagConfig
from kb_core_ui.rag.falkordb_adapter import AdapterError
from kb_core_ui.rag.manager import WorkspaceManager
from kb_core_ui.rag.workspaces import WorkspaceError, WorkspaceRegistry
from kb_core_ui.server import Server, listen_and_serve
from kb_core_ui.store import Store

VALID_KINDS = ("rule", "lesson", "business", "overview", "reference")

_DB_FLAG_USAGE = "path to the SQLite graph DB (default: <repo>/.kb-core-ui/graph.db)"

ROOT_LONG = """kb-core-ui parses a source repo (Go, TypeScript, JavaScript, Python) into a
symbol/call graph — functions, classes, methods, consts, vars, with types,
call edges, and file:line references — stored locally in SQLite under
.kb-core-ui/. It's a companion for both humans (a visual graph explorer) and
AI agents (an MCP server exposing search/get_symbol/get_callers/get_callees
tools) so debugging AI-written code means tracing the graph instead of
re-reading the whole codebase."""

MEMORY_LONG = """kb-core-ui's vector memory holds non-code knowledge — primary codebase
rules, lessons learned, business-logic/data-dependency notes, and what the
software does — as embeddings you can search semantically. It's the
counterpart to the code graph: the graph answers "where does this code
live", memory answers "what do we know that isn't in the code". Kept in
<repo>/.kb-core-ui/memory.db, separate from the graph so re-indexing never
wipes it."""

MCP_LONG = """Runs an MCP server speaking JSON-RPC over stdio, exposing the code graph
(search_symbol, get_symbol, get_file_symbols, get_callers, get_callees,
get_file_slice, get_tree, get_stats) AND the vector memory (memory_search,
memory_add) so an AI agent can query the graph instead of reading whole
files, and recall the codebase's rules and lessons. Point an MCP-capable
client at "kb-core-ui mcp <path>" as the command to launch."""

MEMORY_ADD_LONG = """Add a memory entry. Provide --text, or --from-file to read the body from
a file (or '-' for stdin). Kind is one of: rule, lesson, business,
overview, reference."""

BOT_DOCTOR_LONG = """Runs preflight checks for the whole bot orchestration:
python, the gh CLI (installed + authenticated), the claude CLI (installed +
able to actually get a completion), and kb-core-ui's own MCP server (does it
respond with its tools). Use this to confirm "our app can connect a Claude
session from the terminal" before running any bot."""

BOT_PR_REVIEW_LONG = """Reviews an open GitHub PR's diff with Claude, using kb-core-ui's own MCP
server as the model's source of repo context (search the code graph,
don't read whole files), then posts the findings as a PR comment.

Requires: gh (authenticated), claude (authenticated — a local
`claude login` session, or ANTHROPIC_API_KEY in CI), and a kb-core-ui
binary (this one, or one found on PATH)."""

BOT_GRAPH_SYNC_LONG = """Keeps the code graph fresh and verifies it's sound — the "update graph,
check graph" bot. Re-indexes changed files, then reports resolution
quality and integrity (dangling edges, unresolved-call hotspots). A stale
or broken graph silently makes every AI bot wrong, so this is the
foundation the others depend on.

Runs without AI or authentication."""

BOT_SCRIPTS = {
    "commit-check": "commit_check.py",
    "test-writer": "test_writer.py",
    "anomaly-scan": "anomaly_scan.py",
    "feature-verdict": "feature_verdict.py",
    "triage": "triage.py",
}

# bots.Registry descriptions for the scripts registered as thin passthroughs.
BOT_PASSTHROUGH: list[tuple[str, str]] = [
    (
        "anomaly-scan",
        "Scan the whole codebase for anomalies: possible breakages, "
        "cross-boundary contract mismatches, duplication, and rule violations (from memory).",
    ),
    (
        "commit-check",
        "Review a single commit's diff (same dimensions as PR review) — "
        "run after committing, before pushing.",
    ),
    (
        "feature-verdict",
        "Plan a proposed feature against this codebase: rules it might break, "
        "code to reuse, optimal options, a PRD, and tests to keep current behavior safe.",
    ),
    (
        "test-writer",
        "Generate test cases for a function or file, using the graph to cover real "
        "callers and edge cases. Prints tests (add 'true' to write the file).",
    ),
    (
        "triage",
        "Correlate a GitHub issue to the code via the graph + memory and suggest fixes "
        "with file:line references. (Intercom source planned — needs auth.)",
    ),
]


def _pending(task: str):
    def run(cmd: Command, values: dict, args: list[str]) -> None:
        raise KbError(f"not implemented in the Python port yet (spec/SPEC.md {task})")

    return run


def open_store_and_index(cmd: Command, repo_root: str, db_path: str) -> Store:
    """Opens (creating if needed) the repo's graph DB and runs an incremental
    index pass, printing a one-line progress summary."""
    if not db_path:
        db_path = default_db_path(repo_root)
    ensure_db_dir(repo_root)
    store = Store(db_path)

    cmd.printf(f"Indexing {repo_root}...\n")
    try:
        res = index(repo_root, store)
    except KbError as exc:
        store.close()
        raise KbError(f"index: {exc}") from None
    stats = store.stats()
    cmd.printf(
        f"Indexed {res.files_scanned} files "
        f"({res.files_changed} changed, {res.files_removed} removed) -> "
        f"{stats.symbols} symbols, {stats.edges} edges. DB: {db_path}\n"
    )
    return store


def _run_parse(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path(args)
    open_store_and_index(cmd, repo_root, values["db"]).close()


def open_memory(repo_root: str) -> MemoryStore:
    ensure_db_dir(repo_root)
    return MemoryStore(memory_db_path(repo_root))


def _run_memory_add(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    if not values["title"]:
        raise KbError("--title is required")
    body = values["text"]
    if values["from-file"]:
        if values["from-file"] == "-":
            body = sys.stdin.read()
        else:
            body = Path(values["from-file"]).read_text(encoding="utf-8")
    if not body:
        raise KbError("provide --text or --from-file")
    if values["kind"] not in VALID_KINDS:
        raise KbError(
            f'invalid --kind "{values["kind"]}" '
            "(want: rule|lesson|business|overview|reference)"
        )

    with open_memory(repo_root) as store:
        entry = store.add(values["kind"], values["title"], body, values["source"], memory_now())
    cmd.printf(f"Added memory {entry.id} ({entry.kind})\n")


def _truncate(s: str, n: int) -> str:
    """Collapses whitespace so a multi-line body prints as one tidy line, then
    caps it. The cap counts bytes, as Go's len() does."""
    s = " ".join(s.split())
    raw = s.encode()
    if len(raw) <= n:
        return s
    return raw[:n].decode(errors="replace") + "…"


def _run_memory_search(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    with open_memory(repo_root) as store:
        hits = store.search(args[0], values["kind"], values["top"])
    if not hits:
        cmd.printf("No relevant memory found.\n")
        return
    for h in hits:
        cmd.printf(
            f"\n[{h.score:.2f}] {h.entry.title}  ({h.entry.kind})\n"
            f"  {_truncate(h.entry.text, 200)}\n  id: {h.entry.id}\n"
        )


def _run_memory_list(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    with open_memory(repo_root) as store:
        entries = store.list(values["kind"])
    if not entries:
        cmd.printf("No memory entries yet. Add one with `kb-core-ui memory add`.\n")
        return
    for e in entries:
        cmd.printf(f"{e.kind:<10}  {e.title}\n  {e.id}\n")


def _run_memory_rm(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    with open_memory(repo_root) as store:
        removed = store.remove(args[0])
    if not removed:
        raise KbError(f'no memory with id "{args[0]}"')
    cmd.printf(f"Removed {args[0]}\n")


def locate_bots_dir(explicit: str) -> str:
    """Finds bots/ the way locateWebDir finds web/dist: next to the installed
    entrypoint, in the current working directory, or in this source tree."""
    if explicit:
        return explicit
    here = Path(__file__).resolve()
    candidates = [
        Path(sys.argv[0]).resolve().parent / "bots",
        Path.cwd() / "bots",
        here.parents[3] / "bots",
    ]
    for c in candidates:
        if c.is_dir():
            return str(c)
    raise KbError(
        "bots/ directory not found (looked next to the binary, in cwd, and in "
        "the kb-core-ui source tree) — pass --bots-dir"
    )


def run_bot_script(script_name: str, bots_dir: str, py_args: list[str]) -> None:
    """Execs a bots/*.py script, forwarding stdio and propagating its exit
    code, so `kb-core-ui bot X` behaves like running the script directly."""
    script = Path(locate_bots_dir(bots_dir)) / script_name
    try:
        script.stat()
    except OSError as exc:
        raise KbError(f"bot script not found at {script}: {exc.strerror}") from None
    code = subprocess.call([sys.executable, str(script), *py_args])
    if code != 0:
        raise SystemExit(code)


def _run_bot_doctor(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    py_args = ["--repo", repo_root]
    if values["kb-core-ui-bin"]:
        py_args += ["--kb-core-ui-bin", values["kb-core-ui-bin"]]
    run_bot_script("preflight.py", values["bots-dir"], py_args)


def _run_bot_pr_review(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    py_args = [args[0], "--repo", repo_root]
    if values["kb-core-ui-bin"]:
        py_args += ["--kb-core-ui-bin", values["kb-core-ui-bin"]]
    if values["dry-run"]:
        py_args.append("--dry-run")
    run_bot_script("pr_review.py", values["bots-dir"], py_args)


def _bot_passthrough(script: str):
    """The remaining Python bots parse their own flags, so everything is
    forwarded untouched — with --repo <cwd> injected when absent."""

    def run(cmd: Command, values: dict, args: list[str]) -> None:
        if not any(a == "--repo" or a.startswith("--repo=") for a in args):
            args = args + ["--repo", os.getcwd()]
        run_bot_script(script, "", args)

    return run


def _print_health(cmd: Command, h) -> None:
    cmd.printf("\nGraph health:\n")
    cmd.printf(f"  files:                 {h.files}\n")
    cmd.printf(f"  symbols:               {h.symbols}\n")
    cmd.printf(f"  edges:                 {h.edges}\n")

    # Integrity is the pass/fail signal: dangling edges mean the graph is
    # internally inconsistent. Resolution rate below is informational — calls
    # into stdlib/third-party code correctly stay unresolved.
    if h.dangling_edges == 0:
        cmd.printf("  integrity:             OK (no dangling edges)\n")
    else:
        cmd.printf(f"  integrity:             FAIL ({h.dangling_edges} dangling edges)\n")

    total = h.resolved_calls + h.unresolved_calls
    cmd.printf(
        f"  internal calls linked: {h.resolved_calls} of {total} call sites "
        f"({h.resolution_rate * 100:.0f}% — rest are stdlib/third-party, expected)\n"
    )

    if h.top_unresolved_files:
        cmd.printf(
            "  most external calls (informational — high counts are normal for "
            "glue/IO-heavy files):\n"
        )
        for fc in h.top_unresolved_files:
            cmd.printf(f"    {fc.count:4d}  {fc.path}\n")


def _run_bot_graph_sync(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path([values["repo"]])
    db_path = values["db"] or default_db_path(repo_root)

    changed = removed = 0
    if not values["check-only"]:
        ensure_db_dir(repo_root)
        store = Store(db_path)
        cmd.printf(f"Indexing {repo_root}...\n")
        try:
            res = index(repo_root, store)
        except KbError as exc:
            store.close()
            raise KbError(f"index: {exc}") from None
        finally:
            store.close()
        changed, removed = res.files_changed, res.files_removed
        cmd.printf(
            f"Indexed {res.files_scanned} files "
            f"({res.files_changed} changed, {res.files_removed} removed).\n"
        )

    with Store(db_path) as store:
        health = store.health()
    _print_health(cmd, health)

    if health.dangling_edges > 0:
        raise KbError(
            f"graph integrity check FAILED: {health.dangling_edges} dangling edge(s) "
            f"reference missing symbols — the DB is corrupt; delete {db_path} and re-run"
        )
    # --fail-on-stale lets CI enforce "the committed graph matches the
    # committed code": if re-indexing had to change anything, it was stale.
    if values["fail-on-stale"] and (changed > 0 or removed > 0):
        raise KbError(
            f"graph was stale: re-indexing changed {changed} file(s) and removed "
            f"{removed} — commit a fresh graph or run graph-sync before pushing"
        )


def _repo_flag(usage: str) -> Flag:
    return Flag("repo", "string", ".", usage)


def _bots_flags() -> list[Flag]:
    return [
        _repo_flag("path to the local repo checkout"),
        Flag("bots-dir", "string", "", "path to the bots/ directory (default: auto-detect)"),
        Flag(
            "kb-core-ui-bin",
            "string",
            "",
            "path to the kb-core-ui binary (default: auto-detect)",
        ),
    ]


def _new_parse_cmd() -> Command:
    return Command(
        use="parse [path]",
        short="Parse a repo into the code graph and exit (no server)",
        args=maximum_n_args(1),
        flags=[Flag("db", "string", "", _DB_FLAG_USAGE)],
        run=_run_parse,
    )


def locate_web_dir(explicit: str) -> str:
    """Looks for the built frontend (web/dist) in a few sensible places: next
    to the entrypoint, in the current working directory, or in this source
    tree during local development. Returns "" if none is found."""
    if explicit:
        return explicit
    here = Path(__file__).resolve()
    candidates = [
        Path(sys.argv[0]).resolve().parent / "web" / "dist",
        Path.cwd() / "web" / "dist",
        here.parents[3] / "web" / "dist",
    ]
    for c in candidates:
        if c.is_dir():
            return str(c)
    return ""


def open_browser(url: str) -> None:
    if sys.platform == "darwin":
        argv = ["open", url]
    elif os.name == "nt":
        argv = ["rundll32", "url.dll,FileProtocolHandler", url]
    else:
        argv = ["xdg-open", url]
    try:
        subprocess.Popen(argv)
    except OSError:
        pass  # Go ignores the Start() error too.


def _run_serve(cmd: Command, values: dict, args: list[str]) -> None:
    repo_root = resolve_repo_path(args)
    store = open_store_and_index(cmd, repo_root, values["db"])
    memory = None
    try:
        web_dir = locate_web_dir(values["web-dir"])
        if not web_dir:
            cmd.printf(
                "No built web UI found (looked for web/dist). Serving the API only "
                "— see API_CONTRACT.md, or pass --web-dir.\n"
            )

        # The bot runner re-invokes this same entrypoint, so the web dashboard
        # runs the exact same code paths as the CLI. Go resolves its own
        # executable; the module equivalent is the interpreter plus -m.
        runner = BotRunner([sys.executable, "-m", "kb_core_ui"], repo_root)

        # Memory is best-effort: None just omits the memory endpoints.
        try:
            memory = open_memory(repo_root)
        except KbError as exc:
            cmd.printf(f"Memory unavailable ({exc}) — serving without the memory tab.\n")
            memory = None

        workspace_manager = _default_workspace_manager(repo_root)
        chat_manager = None
        if workspace_manager.config.enabled:
            try:
                from kb_core_ui.rag.chat_manager import ChatManager
            except ModuleNotFoundError as exc:
                if exc.name in {"langgraph", "falkordb", "langchain_falkordb"}:
                    raise KbError(
                        "GraphRAG dependencies are missing; install kb-core-ui[rag]"
                    ) from exc
                raise
            chat_manager = ChatManager(workspace_manager.registry, workspace_manager.config)
        srv = Server(store, repo_root, web_dir, runner, memory, workspace_manager, chat_manager)
        display_host = "localhost" if values["host"] in ("127.0.0.1", "localhost") else values["host"]
        url = f"http://{display_host}:{values['port']}"
        cmd.printf(f"kb-core-ui serving {url}\n")
        if values["open"]:
            open_browser(url)
        listen_and_serve(values["host"], values["port"], srv)
    finally:
        if memory is not None:
            memory.close()
        store.close()


def _new_serve_cmd() -> Command:
    return Command(
        use="serve [path]",
        short="Parse a repo and serve the graph API + web visualizer",
        args=maximum_n_args(1),
        flags=[
            Flag("db", "string", "", _DB_FLAG_USAGE),
            Flag(
                "web-dir",
                "string",
                "",
                "path to the built web UI (web/dist); auto-detected if omitted",
            ),
            Flag("port", "int", 8420, "port to listen on"),
            Flag("host", "string", "127.0.0.1", "host/interface to bind"),
            Flag("open", "bool", True, "open the web UI in a browser on start"),
        ],
        run=_run_serve,
    )


def _run_mcp(cmd: Command, values: dict, args: list[str]) -> None:
    # stdio IS the MCP transport — nothing but the protocol may touch stdout.
    # Command.printf already writes to stderr, which is the same redirect Go
    # makes with cmd.SetOut(os.Stderr).
    repo_root = resolve_repo_path(args)
    store = open_store_and_index(cmd, repo_root, values["db"])
    memory = None
    try:
        # Memory is best-effort: if it cannot open, the graph tools still
        # serve and the memory_* tools are simply absent.
        try:
            memory = open_memory(repo_root)
        except KbError as exc:
            cmd.printf(f"memory unavailable ({exc}) — serving graph tools only\n")
            memory = None

        serve_stdio(McpServer(store, repo_root, memory).handlers())
    finally:
        if memory is not None:
            memory.close()
        store.close()


def _new_mcp_cmd() -> Command:
    return Command(
        use="mcp [path]",
        short="Parse a repo and run an MCP server over stdio for AI agents",
        long=MCP_LONG,
        args=maximum_n_args(1),
        flags=[Flag("db", "string", "", _DB_FLAG_USAGE)],
        run=_run_mcp,
    )


def _new_memory_cmd() -> Command:
    memory = Command(
        use="memory",
        short="Vector memory: store & semantically search codebase rules, lessons, business logic",
        long=MEMORY_LONG,
    )
    memory.add(
        Command(
            use="add",
            short="Add a memory entry",
            long=MEMORY_ADD_LONG,
            args=no_args,
            flags=[
                _repo_flag("repo the memory belongs to"),
                Flag("kind", "string", "lesson", "rule | lesson | business | overview | reference"),
                Flag("title", "string", "", "short title (required)"),
                Flag("text", "string", "", "the memory body"),
                Flag("source", "string", "", "where this came from (person, file, url, bot)"),
                Flag("from-file", "string", "", "read the body from a file, or '-' for stdin"),
            ],
            run=_run_memory_add,
        ),
        Command(
            use="search <query>",
            short="Semantically search memory for the entries most relevant to a query",
            args=exact_args(1),
            flags=[
                _repo_flag("repo to search"),
                Flag("kind", "string", "", "restrict to a kind (optional)"),
                Flag("top", "int", 5, "max results"),
            ],
            run=_run_memory_search,
        ),
        Command(
            use="list",
            short="List memory entries (newest first)",
            args=no_args,
            flags=[
                _repo_flag("repo to list"),
                Flag("kind", "string", "", "restrict to a kind (optional)"),
            ],
            run=_run_memory_list,
        ),
        Command(
            use="rm <id>",
            short="Remove a memory entry by id",
            args=exact_args(1),
            flags=[_repo_flag("repo the memory belongs to")],
            run=_run_memory_rm,
        ),
    )
    return memory


def _new_bot_cmd() -> Command:
    bot = Command(use="bot", short="Run an AI bot (see bots/README.md for the full list)")
    bot.add(
        Command(
            use="doctor",
            short="Verify the orchestration chain: claude connects, gh authed, MCP server responds",
            long=BOT_DOCTOR_LONG,
            args=no_args,
            flags=_bots_flags(),
            run=_run_bot_doctor,
        ),
        Command(
            use="graph-sync",
            short="Re-index the repo graph and check its integrity (no AI, no auth needed)",
            long=BOT_GRAPH_SYNC_LONG,
            args=no_args,
            flags=[
                _repo_flag("path to the local repo checkout"),
                Flag("db", "string", "", _DB_FLAG_USAGE),
                Flag("check-only", "bool", False, "only check the existing graph, don't re-index"),
                Flag(
                    "fail-on-stale",
                    "bool",
                    False,
                    "exit non-zero if re-indexing found changes (CI: enforce a fresh graph)",
                ),
            ],
            run=_run_bot_graph_sync,
        ),
        Command(
            use="pr-review <pr-number>",
            short="Review an open PR's diff and post findings as a comment",
            long=BOT_PR_REVIEW_LONG,
            args=exact_args(1),
            flags=_bots_flags()
            + [
                Flag(
                    "dry-run",
                    "bool",
                    False,
                    "print the review instead of posting it as a PR comment",
                )
            ],
            run=_run_bot_pr_review,
        ),
    )
    for name, short in BOT_PASSTHROUGH:
        bot.add(
            Command(
                use=f"{name} [args...]",
                short=short,
                disable_flag_parsing=True,
                run=_bot_passthrough(BOT_SCRIPTS[name]),
            )
        )
    return bot


def _new_completion_cmd() -> Command:
    """Cobra's auto-registered completion command. Only its name and Short
    reach the recorded baselines (through the root's Available Commands),
    but the shell subcommands are what make those two strings appear."""
    completion = Command(
        use="completion",
        short="Generate the autocompletion script for the specified shell",
        long="Generate the autocompletion script for kb-core-ui for the specified shell.\n"
        "See each sub-command's help for details on how to use the generated script.",
    )
    for shell in ("bash", "fish", "powershell", "zsh"):
        completion.add(
            Command(
                use=shell,
                short=f"Generate the autocompletion script for {shell}",
                args=no_args,
                run=_pending("T12"),
            )
        )
    return completion


def _run_help(cmd: Command, values: dict, args: list[str]) -> None:
    root = cmd
    while root.parent is not None:
        root = root.parent
    target, rest = root.find(args)
    if rest or target is root:
        root.out.write(root.help_string())
    else:
        root.out.write(target.help_string())


def _default_workspace_manager(repo_root: str) -> WorkspaceManager:
    registry = WorkspaceRegistry(workspace_registry_path(repo_root))
    config = RagConfig.from_env(os.environ)
    coordinator = None
    if config.enabled:
        from kb_core_ui.rag.coordinator import IngestionCoordinator

        coordinator = IngestionCoordinator.for_config(registry, config)
    return WorkspaceManager(registry, config, ingestion_coordinator=coordinator)


def _workspace_leaf(use, short, run, *, args=no_args, flags=()):
    common = (Flag("repo", "string", ".", "repository root"),)

    def guarded(cmd: Command, values: dict, positional: list[str]) -> None:
        try:
            manager = cmd.root._workspace_manager_factory(resolve_repo_path([values["repo"]]))
            result = run(manager, values, positional)
        except (WorkspaceError, AdapterError, OSError, ValueError) as exc:
            raise KbError(str(exc)) from None
        cmd.root.out.write(json.dumps(result, separators=(",", ":")) + "\n")

    return Command(use=use, short=short, flags=(*flags, *common), args=args, run=guarded)


def _new_workspace_cmd() -> Command:
    workspace = Command(use="workspace", short="Manage GraphRAG workspaces and sources")
    # Python-only extension; hidden keeps archived Go CLI parity baselines stable.
    workspace.hidden = True
    workspace.add(
        _workspace_leaf(
            "list", "List workspaces", lambda manager, _v, _a: manager.list_workspaces()
        ),
        _workspace_leaf(
            "create <id>",
            "Create workspace",
            lambda manager, values, args: manager.create_workspace(args[0], values["name"]),
            args=exact_args(1),
            flags=(Flag("name", "string", "", "workspace display name"),),
        ),
        _workspace_leaf(
            "delete <id>",
            "Delete workspace and graph",
            lambda manager, _v, args: manager.delete_workspace(args[0]),
            args=exact_args(1),
        ),
        _workspace_leaf(
            "run <workspace> <run>",
            "Get ingestion run status",
            lambda manager, _v, args: manager.get_run(args[0], args[1]),
            args=exact_args(2),
        ),
        _workspace_leaf(
            "health <workspace>",
            "Check workspace graph health",
            lambda manager, _v, args: manager.health(args[0]),
            args=exact_args(1),
        ),
        _workspace_leaf(
            "stats <workspace>",
            "Get workspace graph statistics",
            lambda manager, _v, args: manager.stats(args[0]),
            args=exact_args(1),
        ),
        _workspace_leaf(
            "context <workspace>",
            "Read bounded workspace graph context",
            lambda manager, values, args: manager.graph_context(
                args[0],
                source_ids=([values["source"]] if values["source"] else []),
                limit=values["limit"],
            ),
            args=exact_args(1),
            flags=(
                Flag("source", "string", "", "optional source id"),
                Flag("limit", "int", 50, "maximum records (1-200)"),
            ),
        ),
    )
    source = Command(use="source", short="Manage workspace sources")
    source.add(
        _workspace_leaf(
            "add <workspace> <source>",
            "Add source",
            lambda manager, values, args: manager.add_source(
                args[0], args[1], values["kind"], values["uri"], values["ref"]
            ),
            args=exact_args(2),
            flags=(
                Flag("kind", "string", "", "source kind"),
                Flag("uri", "string", "", "source URI"),
                Flag("ref", "string", "", "source revision"),
            ),
        ),
        _workspace_leaf(
            "remove <workspace> <source>",
            "Remove source and graph records",
            lambda manager, _v, args: manager.remove_source(args[0], args[1]),
            args=exact_args(2),
        ),
        _workspace_leaf(
            "refresh <workspace> <source>",
            "Queue source refresh",
            lambda manager, _v, args: manager.refresh_source(args[0], args[1]),
            args=exact_args(2),
        ),
    )
    ingestion = Command(use="ingestion", short="Control ingestion runs")
    ingestion.add(
        _workspace_leaf(
            "start <workspace> <source>",
            "Queue ingestion",
            lambda manager, _v, args: manager.start_ingestion(args[0], args[1]),
            args=exact_args(2),
        ),
        _workspace_leaf(
            "cancel <workspace> <run>",
            "Cancel ingestion",
            lambda manager, _v, args: manager.cancel_ingestion(args[0], args[1]),
            args=exact_args(2),
        ),
    )
    workspace.add(source, ingestion)
    return workspace


def build_root(workspace_manager_factory=None) -> Command:
    root = Command(
        use="kb-core-ui",
        short="AI Code Knowledge Graph & Visual Debugger",
        long=ROOT_LONG,
    )
    root._workspace_manager_factory = workspace_manager_factory or _default_workspace_manager
    root.add(
        _new_parse_cmd(),
        _new_serve_cmd(),
        _new_mcp_cmd(),
        _new_bot_cmd(),
        _new_memory_cmd(),
        _new_workspace_cmd(),
        _new_completion_cmd(),
        Command(use="help [command]", short="Help about any command", run=_run_help),
    )
    return root
