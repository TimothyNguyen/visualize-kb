# visualize-kb

Visualize multiple repos easily with high performance via UI

py -m venv .venv-core
.venv-core/bin/python -m pip install -e ./kb-core

py -m venv .venv-ui
.venv-ui/bin/python -m pip install -e ./kb-core-ui/python

Frontend:
source .venv-core/bin/activate
py kb-core-ui/dev.py frontend .

Folder lookup:

`GET /api/folders` lists folders under current repo root. Set
`KB_ALLOWED_FOLDER_ROOTS` to a path-separated list of trusted roots to select
other local repos or document folders.

## FalkorDB

Optional local FalkorDB development setup: [docs/falkordb-development.md](docs/falkordb-development.md).
