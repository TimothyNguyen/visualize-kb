# FalkorDB development

Run a local FalkorDB server and browser from the repository root:

```bash
docker compose -f compose.falkordb.yml up -d --wait
docker compose -f compose.falkordb.yml ps
```

FalkorDB listens on `falkordb://localhost:6379`. Its browser is available at
`http://localhost:3000`. Both ports bind to loopback only. Graph data persists
in the Compose-managed `falkordb-data` volume.

Install the optional client and push an existing KB Core graph:

```bash
source .venv-core/Scripts/activate  # Windows Git Bash
python -m pip install -e "./kb-core[falkordb]"
python -m kb_core export falkordb --graph ./kb-core-out/graph.json \
  --push falkordb://localhost:6379
```

On macOS or Linux, activate with `source .venv-core/bin/activate` instead.
The default FalkorDB graph name is `kb-core`; pushes use `MERGE` and are safe
to repeat.

Inspect server state:

```bash
docker compose -f compose.falkordb.yml exec falkordb redis-cli ping
docker compose -f compose.falkordb.yml logs -f falkordb
```

Stop the service while retaining data:

```bash
docker compose -f compose.falkordb.yml down
```

Delete persisted development data only when intentionally resetting the graph:

```bash
docker compose -f compose.falkordb.yml down -v
```

## UI integration direction

Keep browser clients behind `kb-core-ui`'s Python API. Do not expose FalkorDB
credentials or Redis protocol access to the browser. Add a graph-store interface
inside the API with the current JSON implementation as the default and an
optional FalkorDB implementation for server-side search, traversal, pagination,
and incremental graph loading. This preserves offline startup and existing API
contracts while allowing large graphs to avoid full-file parsing and transfer.
