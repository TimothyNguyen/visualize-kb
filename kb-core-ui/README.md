# KB Core UI

Full UI migration for KB Core. React reads KB Core's `kb-core-out/graph.json`
directly, visualizing files, symbols, edges, callers, callees, search results,
and focused subgraphs.

Repository retains migrated Go, MCP, bot, memory, API, workflow, and test
source under `kb-core-ui`. Its SQLite state lives in `.kb-core-ui/`, avoiding
conflicts with KB Core's `kb-core-out/` artifacts.

## Architecture

```
kb-core extract <repo>  ->  <repo>/kb-core-out/graph.json
                                  |
                                  v
web/ React + Vite       ->  KB Core UI graph explorer
```

## Run UI

```powershell
kb-core extract <repo> --code-only
Copy-Item <repo>\kb-core-out\graph.json .\web\public\kb-core-out\graph.json
cd .\web
npm install
npm run dev
```

Open `http://localhost:5173`. Set `VITE_KB_CORE_GRAPH_URL` for another served
graph URL.

## Migrated Go services

```powershell
go build -o kb-core-ui.exe .\cmd\kb-core-ui
.\kb-core-ui.exe serve <repo> --open=false
```

Go service retains REST, MCP, bot, and memory commands under `kb-core-ui`.
React graph data remains sourced from KB Core `graph.json`.

## Verify

```powershell
go test ./...
cd web; npm run build
```
