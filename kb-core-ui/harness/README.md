# kb-core-ui parity harness

Dual-process Go-vs-Python parity harness for `kb-core-ui` (SPEC.md T3/T4).

Only a `go` engine exists today (no Python candidate yet — see SPEC.md T5-T11).
The harness proves its own correctness via Go-vs-Go self-tests.

## Setup

```
cd kb-core-ui && go build -o kb-core-ui.exe ./cmd/kb-core-ui
cd harness && pip install -e ".[dev]"
```

## Usage

```
python -m harness record --fixtures-dir tests/fixtures
python -m harness verify --fixtures-dir tests/fixtures
python -m harness parity --fixtures-dir tests/fixtures --oracle go --candidate go
python -m harness report --in .harness-work/runs/<run>/report.json
pytest
```
