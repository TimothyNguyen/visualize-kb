# kb-core-ui parity harness

Dual-process Go-vs-Python parity harness for `kb-core-ui` (spec/SPEC.md T3/T4).

Python is the default application runtime. The `go` engine runs the archived
module in `../legacy/go/`; Go-vs-Go self-tests also validate the harness.

## Setup

```
cd kb-core-ui/legacy/go
go build -o kb-core-ui.exe ./cmd/kb-core-ui
cd ../../harness
python -m pip install -e "../python[dev]" -e ".[dev]"
```

Use `-o kb-core-ui` on Linux/macOS. The oracle resolves from `legacy/go/`,
or an explicit `--go-bin` / `KB_CORE_UI_BIN` override. Overrides must name
a real Go build. PATH is deliberately ignored: the Python package installs
a console script named `kb-core-ui`, so PATH discovery could compare Python
against itself and silently report false parity. `go version -m <binary>`
can confirm Go build metadata.

## Usage

```
python -m harness record --fixtures-dir tests/fixtures
python -m harness verify --fixtures-dir tests/fixtures
python -m harness parity --fixtures-dir tests/fixtures --oracle go --candidate python
python -m harness report --in .harness-work/runs/<run>/report.json
python -m pytest -q
```

`record` rewrites baselines; use it only when intentionally recording oracle
behavior. `verify` replays baselines against the engine/platform that recorded
them (currently Windows). CI uses only same-machine `parity` because OS MIME
types and error messages can differ. Every run isolates roots and databases.

The active CI workflow is `../../.github/workflows/parity.yml`. The nested
`../.github/workflows/` bot examples remain inactive.

## Dynamic RAG workflow

Replay workspace creation, graph normalization, FalkorDB upsert/read/delete,
registry persistence, and graph cleanup as one required-stage workflow:

```
python -m harness rag --backend fake
```

Run same workflow against FalkorDB on `127.0.0.1:6379`:

```
RAG_ENABLE=true FALKORDB_URL=falkor://127.0.0.1:6379 python -m harness rag --backend falkordb
```

Both modes write machine-readable `kb-core.rag-harness.v1` reports. CI runs
fake mode plus pinned `falkordb/falkordb:v4.20.4` service mode in
`../../.github/workflows/rag-harness.yml`.
