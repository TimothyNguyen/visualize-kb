# Local GraphRAG dev stack

`docker-compose.yml` (in `kb-core-ui/`) runs FalkorDB, seeds a demo workspace,
and serves the UI. It defaults to mocked models, so it needs no provider
account and no API key.

## Start

```bash
pnpm -C web install && pnpm -C web build   # the image ships a prebuilt bundle
docker compose up --build
```

Then open <http://localhost:8420> and pick the **demo** workspace on `/chat`.

Services:

| service | what it does | health |
| --- | --- | --- |
| `falkordb` | pinned `falkordb/falkordb:v4.20.4`, data in the `falkordb-data` volume | `redis-cli ping` |
| `seed` | runs `kb-core-ui workspace seed` once, then exits 0 | exit status |
| `kb-core-ui` | serves the API + built web UI on `127.0.0.1:8420` | `GET /api/stats` |

`kb-core-ui` waits for FalkorDB to report healthy and for `seed` to finish, so
`docker compose up` reaches a working chat without any manual step.

## Seeding

The seed manifest is `deploy/seed/workspace.json`. It lists a `local_repo`
source (`deploy/seed/repo`) and a `document_set` source (`deploy/seed/docs`).
Relative URIs resolve against the manifest, so the same file works from the
container, from the host, and from the harness.

Seeding runs through the normal `WorkspaceManager` and `IngestionCoordinator`
path — the same one the CLI and the HTTP API use — and it is idempotent:
re-running refreshes the existing sources instead of failing.

```bash
# re-seed in place (refresh)
docker compose run --rm seed

# drop the workspace graph and rebuild it
docker compose run --rm seed kb-core-ui workspace seed \
  --repo /app/data --fixture /app/deploy/seed/workspace.json --reset

# same thing on the host, against your own manifest
kb-core-ui workspace seed --repo . --fixture path/to/workspace.json
```

## Reset and migration

There is no schema migration step: ingestion writes a new version of a source
and deletes the records that source previously owned, so re-seeding converges.
To go further:

```bash
# forget one workspace, keep the rest
docker compose exec kb-core-ui kb-core-ui workspace delete demo --repo /app/data

# stop the stack, keep all data
docker compose down

# stop the stack and delete FalkorDB data + the workspace registry
docker compose down -v
```

Upgrading the FalkorDB tag is a `down -v` plus a re-seed. Do not bump the tag
in isolation — it is pinned to match the `falkordb-backend` job in
`.github/workflows/rag-harness.yml`, and the RAG harness asserts the two agree.

## Optional real provider

Copy `.env.example` to `.env` and uncomment what you need. Those variables are
server-only: the browser talks to the kb-core-ui backend and never to FalkorDB
or a provider API, so no credential belongs in a `VITE_*` variable or in the
web bundle.

```bash
cp .env.example .env
# edit RAG_LLM_PROVIDER / RAG_LLM_MODEL / RAG_EMBEDDING_MODEL and the key
docker compose up -d
```

Leaving `.env` alone keeps `RAG_LLM_PROVIDER=fake` and
`RAG_EMBEDDING_MODEL=fake`, which is what CI runs.

## Troubleshooting

- `docker compose ps` shows `falkordb` unhealthy: FalkorDB never accepted a
  ping. Check `docker compose logs falkordb` and that host port 6379 is free.
- `seed` exits non-zero: read `docker compose logs seed`. A missing
  `graph.json` under a `local_repo` source and an unreadable manifest both
  report the offending path.
- Chat replies "GraphRAG is disabled": `RAG_ENABLE` did not reach the
  container, usually from an `.env` that overrides it.
- The UI loads but is blank: `web/dist` was stale or missing at build time.
  Rebuild the bundle and re-run `docker compose build`.
