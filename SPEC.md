# Go to Python Parity Migration

## §G

G1. Replace `kb-core-ui` Go backend with Python. Keep React UI contract. Prove parity through dynamic Go-vs-Python harness. Move Go source to `kb-core-ui/legacy/go/` after cutover.

## §C

C1. Go stays runnable oracle until Python passes full parity suite.

C2. Python keeps current CLI, REST, MCP, SQLite, graph, parser, bot, memory behavior.

C3. Harness runs Go and Python as separate processes with isolated temp roots and databases.

C4. Comparison uses canonical output. Ignore fields only per named case.

C5. React TypeScript API types and visible behavior stay compatible through cutover.

C6. `legacy/go` stays read-only after move. Harness can still run it for regression comparison.

C7. No Go removal, default-runtime switch, or legacy move before all required parity gates pass.

## §I

I.cli. Current `kb-core-ui` command behavior, including `serve`, `parse`, `mcp`, and shared store/index setup.

I.rest. Current graph, tree, symbol, source, search, stats, bot, and memory HTTP routes.

I.mcp. Current `tools/list` schema and every graph/memory tool result.

I.graph. Parser symbols, source ranges, IDs, references, calls, graph nodes, graph edges, and JSON output.

I.store. Code-index and memory SQLite schemas, migrations, query behavior, vector encoding, and lifecycle behavior.

I.react. `web/src/api/client.ts` request/response contract.

I.harness. `record`, `parity`, `verify`, and `report` modes; fixture manifests; canonicalizer; structured diffs.

I.legacy. `kb-core-ui/legacy/go/` module and explicit oracle-runner path.

## §V

V1. Same fixture plus same declared operation yields equivalent canonical Go and Python results.

V2. Harness normalizes only declared nondeterminism: key order, line endings, fixture-root paths, timestamps, generated IDs, and Go map-iteration order.

V3. Harness fails unknown output differences. No global ignore list.

V4. Each oracle/candidate run gets separate temp root and SQLite database.

V5. Python preserves externally visible CLI exit code, REST status/error schema, MCP tool schema/result, and graph JSON schema.

V6. Parser parity preserves symbol kind, qualified name, source span, signature, docstring/comment behavior, references, and calls.

V7. Index parity covers first index, changed-file reparse, unchanged-file skip, deleted-file prune, and persistent-store reopen.

V8. Existing Go unit/integration behavior gets Python tests or dynamic parity coverage before cutover.

V9. React works against Python without TypeScript API contract changes.

V10. Python becomes default only when required parity cases pass in CI.

V11. Legacy move preserves complete runnable Go module under `kb-core-ui/legacy/go/`.

## §T

|id|status|task|cites|
|---|---|---|---|
|T1|x|Capture Go CLI help, REST, MCP `tools/list`, graph JSON, and error baseline fixtures.|V1,V5|
|T2|x|Create fixture repositories for Go, Python, TypeScript, mixed-language, malformed, changed, and deleted-file cases.|V1,V6,V7|
|T3|x|Build canonicalizer and structured JSON diff reporter with per-case normalizer allowlist.|V2,V3|
|T4|x|Build dual-process harness: `record`, `parity`, `verify`, `report`; isolated temp roots and databases.|V1,V4|
|T5|x|Create Python package, configuration, typed models, error model, and CLI skeleton.|V5|
|T6|x|Port parser dispatch and Go/Python/TypeScript extraction. Add parser parity cases.|V6,V8|
|T7|x|Port graph builder, code indexer, SQLite code store, migrations, and incremental index behavior.|V7,V8|
|T8|x|Port memory store, embedding interface, CRUD/search behavior, and bot runner behavior.|V5,V8|
|T9|x|Port REST service. Run route parity cases against Go and Python.|V5,V8|
|T10|.|Port MCP service. Run tool-list, schema, graph-tool, and memory-tool parity cases.|V5,V8|
|T11|.|Run React against Python. Keep client types and visible flows compatible.|V9|
|T12|.|Gate Python default-runtime switch on CI parity. Move Go module to `kb-core-ui/legacy/go/`; retain optional legacy oracle suite.|V10,V11|

## §B

|id|date|cause|fix|
|---|---|---|---|
|B1|2026-08-28|harness subprocess `text=True` w/o `encoding` → child stdout decoded via OS locale (cp1252 on win). Go emits UTF-8 ∴ `—` baselined as mojibake `â€”`|`encoding="utf-8"` on all child procs in `runner.py` + `mcp_client.py`|
|B2|2026-08-28|CLI capture was `stdout_exit` only, but Cobra `cmd.Print*` → `OutOrStderr()` = stderr ∴ ∀ CLI baseline recorded `stdout: ""`|new capture `stdout_stderr_exit`|
|B3|2026-08-28|grammar skew: `tree-sitter-go` 0.25 leaves trailing `// c` as prev-sibling of next spec, pinned `smacker` grammar ⊥ ∴ py gave `B = 2 // c` doc to `C`|`_is_trailing` guard in `parser/common.py::leading_comment`|
|B4|2026-08-28|Go `encoding/json` HTML-escapes `<` `>` `&` → `<` `>` `&`. py `json.dumps` ⊥ ∴ `params_json` w/ `Promise<T>` ≠ go bytes|! go-compatible dumps helper ∀ DB writes & REST bodies (T7)|
|B5|2026-08-28|py `sqlite3.connect` defaults `check_same_thread=True`; `serve` dispatches ∀ req on own thread ∴ ∀ REST call → 500, empty body|`check_same_thread=False` on both stores + RLock ∀ dispatch in `server/app.py` (go `*sql.DB` = pool)|
|B6|2026-08-28|go `Store.Subgraph` builds edges by ranging `map[graph.Edge]bool`; go randomizes map iter ∴ `/api/graph/subgraph` edge order ⊥ stable, go ≠ go|new per-case normalizer `edge_order`, declared on subgraph cases only. `/api/graph` reads edges from SQLite ∴ stays unnormalized (V3)|
|B7|2026-08-28|`verify` ran ∀ op in own RunContext, but `record`/`parity` share 1 ctx ∀ fixture ∴ stateful op (POST `/api/memory` → GET `/api/memory`) compared vs ≠ preconditions → false FAIL|`verify` replays whole fixture in 1 ctx per engine, diffs only ops w/ baseline for that engine|
