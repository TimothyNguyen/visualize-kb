# KB Core UI

Full UI migration for KB Core. React reads KB Core's `kb-core-out/graph.json`
directly, visualizing files, symbols, edges, callers, callees, search results,
and focused subgraphs.

Python provides the CLI, REST, MCP, bot, and memory runtime. The unchanged
Go module is retained in `legacy/go/` as a read-only parity oracle.
SQLite state lives in `.kb-core-ui/`, avoiding
conflicts with KB Core's `kb-core-out/` artifacts.

## Architecture

```
kb-core extract <repo>  ->  <repo>/kb-core-out/graph.json
                                  |
                                  v
web/ React + Vite       ->  KB Core UI graph explorer
```

## Run UI

`kb-core` and `kb-core-ui` use incompatible `tree-sitter` versions, so install
them into separate virtual environments:

```bash
python -m venv .venv-core
.venv-core/bin/python -m pip install -e ./kb-core

python -m venv .venv-ui
.venv-ui/bin/python -m pip install -e ./kb-core-ui/python
```

On Windows, replace `.venv-*/bin/python` with `.venv-*\\Scripts\\python.exe`.

For frontend-only development, run with the core environment:

```bash
.venv-core/bin/python kb-core-ui/dev.py frontend .
```

For the API plus built UI, activate the UI environment and append the core
environment's executable directory to `PATH`:

```bash
. .venv-ui/bin/activate
PATH="$PATH:$(pwd)/.venv-core/bin" .venv-ui/bin/python kb-core-ui/dev.py serve .
```

On Windows PowerShell:

```powershell
.\.venv-ui\Scripts\Activate.ps1
$env:PATH += ";$((Resolve-Path .\.venv-core\Scripts).Path)"
python kb-core-ui/dev.py serve .
```

The launcher extracts `graph.json`, copies it into `web/public/kb-core-out/`,
installs frontend deps on first run, and starts Vite on
`http://localhost:5173` for `frontend`. `serve` builds `web/dist` and starts
the API serving that bundle.
Set `VITE_KB_CORE_GRAPH_URL` for another served graph URL.

## Phone Testing

Put computer and phone on the same Wi-Fi network. In Git Bash, run the
frontend with LAN binding:

```bash
source .venv-core/Scripts/activate
VITE_HOST=0.0.0.0 python kb-core-ui/dev.py frontend kb-core
```

Open `http://<computer-lan-ip>:5173` on the phone. Find the computer address
with `ipconfig` on Windows or `ifconfig`/`ip addr` on macOS/Linux.

For the API plus built UI, use the UI environment and expose both services:

```bash
source .venv-ui/Scripts/activate
export PATH="$PATH:$(pwd)/.venv-core/Scripts"
export KB_CORE_UI_HOST=0.0.0.0
python kb-core-ui/dev.py serve kb-core
```

Open `http://<computer-lan-ip>:8420` on the phone. Stop the server with
`Ctrl-C`; keep LAN binding limited to trusted networks.

## Python services (default)

From `kb-core-ui/`, install with Python 3.10+ in an activated virtual
environment. Keep this source checkout for the bot scripts and web assets.

```bash
python -m pip install -e "./python[dev]"
python kb-core-ui/dev.py serve <repo>
kb-core-ui mcp <repo>
```

`python -m kb_core_ui` invokes the same runtime if the console script is not
on PATH. Bots select this interpreter's installed Python console script;
`--kb-core-ui-bin` explicitly selects another executable. Old root-level Go
builds and Go executables on PATH are not selected by the bots. The `serve`
launcher builds `web/dist`, then runs the Python API server with that static
bundle. The UI launcher does not require `kb-core` and `kb-core-ui` to share one
environment; that combination conflicts on `tree-sitter` versions.

React graph data remains sourced from KB Core `graph.json`. API client types
and REST/MCP contracts remain unchanged.

## Optional Go oracle

Build from `legacy/go/` with `go build -o kb-core-ui.exe ./cmd/kb-core-ui`
(use `kb-core-ui` without `.exe` on Linux/macOS). Keep its build output there.
The harness discovers this explicit legacy path, never PATH. See
[legacy/README.md](legacy/README.md) for the CI gate evidence and rollback.

## Verify

```powershell
cd python
python -m pytest -q
cd ../harness
python -m pip install -e ".[dev]"
python -m pytest -q
python -m harness parity --oracle go --candidate python
python -m harness verify
cd ../web
npm run build
```

Parity requires the optional Go oracle. `verify` replays the committed
Windows baselines locally; CI gates on same-machine `parity`, not `verify`.
