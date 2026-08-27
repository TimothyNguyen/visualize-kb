# KB Core investigation doc

This doc captures the current end-to-end trace of `kb-core` behavior in this repo, plus open drill points.

Repo state:

- Repo root: `C:\Users\quynh\OneDrive\Desktop\swe-workspace\op-kb\kb-core`
- Existing graph present: `kb-core-out/graph.json`
- Existing report present: `kb-core-out/GRAPH_REPORT.md`
- `.codegraph/` not present in repo root
- Current worktree already has unrelated edits:
  - `kb_core/affected.py`
  - `kb_core/cli.py`
  - `kb_core/serve.py`
  - `tests/bench_query_scoring.py`
  - `tests/fixtures/obj/`

## High-level shape

`kb-core` is a pipeline plus query layer:

1. detect corpus
2. extract code and semantic content
3. merge extraction into graph
4. cluster graph
5. generate report and visual exports
6. answer query/path/explain against built graph

The graph already exists, so corpus questions should go through query mode, not rebuild mode.

## Core outputs

Main artifacts:

- `kb-core-out/graph.json`
- `kb-core-out/GRAPH_REPORT.md`
- `kb-core-out/graph.html`
- `kb-core-out/.kb_core_analysis.json`
- `kb-core-out/.kb_core_labels.json`
- `kb-core-out/cost.json`

## CLI command surface

`kb_core/cli.py` includes these subcommands:

- `prs`
- `hook`
- `query`
- `affected`
- `save-result`
- `reflect`
- `path`
- `explain`
- `diagnose`
- `add`
- `watch`
- `update`
- `hook-check`
- `hook-guard`
- `check-update`
- `tree`
- `merge-driver`
- `merge-graphs`
- `clone`
- `export`
- `benchmark`
- `global`
- `extract`
- `cache-check`
- `merge-chunks`
- `merge-semantic`

Tail branch findings:

- `cache-check`
  - reads file list from disk
  - calls semantic cache lookup
  - writes `.kb_core_cached.json`
  - writes `.kb_core_uncached.txt`

- `merge-chunks`
  - loads chunk JSON from semantic subagents
  - validates each chunk with `load_validated_semantic_fragment`
  - skips invalid chunks with warning
  - deduplicates nodes by `id`
  - sums token counts

- `merge-semantic`
  - merges cached semantic result and fresh semantic result
  - cached node ids win on duplicate
  - writes merged semantic JSON

- direct path invocation
  - `kb-core <path>` reenters as `extract`

## Extraction architecture

### Registry

`kb_core/extractors/__init__.py` is the registry for per-language extractors.

It currently exposes:

- `extract_apex`
- `extract_bash`
- `extract_blade`
- `extract_dart`
- `extract_delphi_form`
- `extract_dm`
- `extract_dmf`
- `extract_dmi`
- `extract_dmm`
- `extract_elixir`
- `extract_fortran`
- `extract_go`
- `extract_json`
- `extract_julia`
- `extract_lazarus_form`
- `extract_markdown`
- `extract_objc`
- `extract_pascal`
- `extract_powershell`
- `extract_powershell_manifest`
- `extract_razor`
- `extract_rust`
- `extract_sln`
- `extract_sql`
- `extract_terraform`
- `extract_verilog`
- `extract_zig`

### Migration status

`kb_core/extractors/MIGRATION.md` says migration is partial.

Migrated yes:

- blade
- zig
- elixir
- razor
- dart
- rust
- go
- powershell
- fortran
- sql
- dm
- bash
- apex
- terraform
- sln
- pascal_forms
- json_config

Still not split out as separate modules:

- config-driven core languages:
  - python
  - js
  - java
  - c
  - cpp
  - ruby
  - csharp
  - kotlin
  - scala
  - php
  - lua
  - swift
  - groovy

- other bespoke not yet moved:
  - julia
  - verilog
  - markdown
  - objc
  - csproj
  - slnx
  - lazarus_package
  - pascal

### `extract.py` shape

`kb_core/extract.py` is still the central dispatcher.

Notable facts:

- `_DISPATCH` maps suffixes to extractors
- `_get_extractor()` handles ambiguous `.h`, `.m`, `.mm`, and other sniffed cases
- `_extract_parallel()` and `_extract_sequential()` drive actual corpus extraction
- `collect_files()` enumerates files
- `extract()` orchestrates file classification and extraction
- migration block re-exports moved extractors from `kb_core/extractors/*`
- `extract.py` still owns the shared config-driven core and many bespoke extractors

Important routing details:

- `.h` may route to C, C++, or ObjC based on content
- `.m` may route to ObjC or MATLAB-like handling depending on sniffing
- `.skill` routes to markdown
- `.md`, `.mdx`, `.qmd` route to markdown
- `.ps1`, `.psm1` route to PowerShell
- `.psd1` routes to PowerShell manifest extractor
- `.slnx` and `.csproj` have dedicated handlers

Header/source sniffing:

- `_is_objc_header()` checks `.h` for ObjC markers and routes to ObjC when found
- `_is_cpp_header()` upgrades `.h` to C++ when class-like markers appear
- `_is_objc_source()` checks `.m` for ObjC markers so MATLAB-like `.m` files do not get force-parsed as ObjC
- `_get_extractor()` applies those sniffers before falling back to suffix table

## Shared extraction helpers

`kb_core/extractors/base.py` provides shared helpers like:

- `_make_id`
- `_file_stem`
- `_read_text`
- built-in global / builtin symbol handling

`kb_core/extractors/models.py` defines:

- `LanguageConfig`
- symbol resolution fact types
- `_JS_CACHE_BYPASS_SUFFIXES`
- workspace package cache

`kb_core/extractors/resolution.py` handles language-specific resolution helpers, especially JS/TS config aliasing and baseUrl behavior.

`kb_core/extractors/engine.py` is the shared extraction core for config-driven languages.

## Query and question generation

`kb_core/analyze.py` drives report questions.

`suggest_questions()` emits questions from:

1. AMBIGUOUS edges
2. bridge nodes with high betweenness
3. god nodes with many INFERRED edges
4. isolated or weakly connected nodes
5. low-cohesion communities

Question examples:

- "What is the exact relationship between `X` and `Y`?"
- "Why does `BridgeNode` connect `Community A` to `Community B`?"
- "Are the inferred relationships involving `Node` actually correct?"
- "What connects `NodeA`, `NodeB` to the rest of the system?"
- "Should `Community` be split into smaller modules?"

`kb_core/report.py` then renders those into the `## Suggested Questions` section.

## Language-specific findings

### Markdown

`kb_core/extractors/markdown.py` is a pure line parser.

It does not depend on AST parsers.

### Go

`kb_core/extractors/go.py` includes:

- `_GO_PREDECLARED_TYPES`
- `_GO_PREDECLARED_FUNCS`
- Go-specific collection and extraction logic

Important Go behavior:

- predeclared functions are filtered only for bare identifiers
- the filter is local to Go, not added to shared builtin globals
- `append`, `len`, `make`, `new`, `print`, etc. are treated as shadowing hazards

### Python / JS / TS family

These remain on the shared config-driven core in `extract.py`.

Observed behavior:

- `extract_python()` adds rationale nodes for autogenerated Python and import reasoning
- `extract_js()` has dynamic import rescue logic
- Svelte/Astro/Vue handlers reuse JS-like extraction plus special rescue/masking paths

### Java / Groovy / C / C++ / C# / Kotlin / Scala / PHP / Lua / Swift

These use `_extract_generic` plus language-specific config and helper passes.

Observed behavior:

- C# has namespace and partial-class canonicalization
- Swift has extension merging and call resolution
- Kotlin has package/import/qualified-call resolution helpers
- C/C++ have type-ref collection and member-call resolution helpers
- PHP has method return type and type collection helpers

## Build and graph pipeline

### `build.py`

`build_from_json()` is the main graph builder.

It is used in both full build and incremental update flows.

### `cluster.py`

`cluster()`:

- uses Leiden if available
- falls back to Louvain
- handles isolates
- handles hubs
- splits oversized communities
- does a low-cohesion second pass
- reindexes communities deterministically

`label_communities_by_hub()` names communities by highest-degree member.

`score_all()` and `cohesion_score()` are used to quantify community quality.

### `analyze.py`

Used for:

- god nodes
- surprising connections
- suggestion generation

`graph_diff()` exists too, for comparing graph snapshots.

### `report.py`

`generate()` assembles:

- corpus summary
- extraction confidence percentages
- token cost
- graph freshness
- community hubs
- god nodes
- surprising connections
- import cycles
- hyperedges
- community sections
- ambiguous edges
- gaps
- work-memory overlay when learning data exists

### `diagnostics.py`

`diagnose_extraction()` checks:

- dangling endpoints
- missing endpoints
- self-loops
- directed collapse risk
- undirected collapse risk
- unverified nodes
- producer suppression sites

`format_diagnostic_report()` and `format_diagnostic_json()` are renderers.

`diagnose_extraction()` is the integrity gate for extraction output, not graph query.

## Export stack

`kb_core/export.py` is the main export layer.

Key pieces:

- `backup_if_protected()`
  - snapshots protected artifacts before overwrite
  - triggers when semantic marker exists or labels are curated

- `attach_hyperedges()`
  - stores hyperedges in graph metadata

- `MALFORMED_GRAPH`
  - sentinel for unreadable non-empty existing graph.json

- `existing_graph_node_count()`
  - counts nodes safely
  - fails closed on malformed graphs
  - returns `None` for absent/empty/oversized graphs

- `to_json()`
  - writes graph.json
  - restores true edge direction from `_src` / `_tgt`
  - writes community names when labels are present
  - keeps built_at_commit
  - refuses silent shrink
  - treats malformed existing graph as fail-closed
  - treats oversize existing graph as replaceable because compare would be unsafe

- `to_cypher()`
  - writes Neo4j import Cypher

- `to_obsidian()`
  - writes Obsidian vault notes

- `to_canvas()`
  - writes Obsidian canvas output

- `to_graphml()`
  - writes GraphML

- `to_svg()`
  - writes SVG export

- `to_html()`
  - HTML visualization
  - can aggregate into community view for large graphs

Direct graph database push:

- `push_to_neo4j()` uses Neo4j Python driver
- `push_to_falkordb()` uses FalkorDB SDK

Both sanitize labels and relation types before emitting Cypher-like writes.

`kb_core/exporters/graphdb.py` provides direct push helpers:

- `push_to_neo4j()`
- `push_to_falkordb()`

`kb_core/exporters/base.py` holds shared palette constants like `COMMUNITY_COLORS`.

## Serve / query / path / explain

`kb_core/serve.py` is the interactive graph query engine.

Observed functions and roles:

- `_score_nodes()`
  - ranks seed nodes for query/path/explain

- `_pick_scored_endpoint()`
  - picks best path endpoint by score

- `_pick_seeds()`
  - chooses BFS seeds and ensures each term gets representation

- `_bfs()` / `_dfs()`
  - graph traversal backends

- `_subgraph_to_text()`
  - renders traversal result in seed-first order

- `_shortest_path_text()`
  - shortest path rendering
  - preserves true stored relation direction using `_src` / `_tgt`

- `_find_node_tiers()` / `_find_node()`
  - explain lookup

- `find_node_ambiguity()`
  - detects same-label, different-file ambiguity

CLI mapping:

- `query` uses `_query_graph_text()`
- `path` uses `_shortest_path_text()`
- `explain` uses `_find_node()`

`_shortest_path_text()` uses true stored edge direction when rendering a found path.

## Affected-node logic

`kb_core/affected.py`:

- `resolve_seed()` finds node by label / source file / bare name
- `affected_nodes()` reverse-walks incoming edges for relation sets
- seeds class/member nodes via `contains` and `method`
- `format_affected()` prints actual matched source locations

## Watch / rebuild flow

`kb_core/watch.py` handles auto-rebuild.

Trace so far:

- `_rebuild_code()` drives detect → reconcile → build → cluster → generate → export
- `_reconcile_existing_graph()` preserves semantic-backed docs and handles stale/ignored files
- `_check_shrink()` blocks unexplained graph loss
- `watch()` calls `_rebuild_code()` and handles manifest saving

`_check_shrink()` blocks unexplained loss but allows legitimate shrink when files were removed.

## Query/report facts from graph output

Known high-degree / hub-like nodes in `kb-core-out/GRAPH_REPORT.md`:

- `extract()` has largest edge fanout
- `build_from_json()` next large hub
- `_rebuild_code()`
- `_read_text()`
- `_make_id()`
- `_file_stem()`
- `detect()`
- `main()`
- `ingest_scip_json()`
- `extract_js()`

The report also surfaces:

- god nodes
- surprising connections
- suggested questions

Current graph-report hub list already observed:

- `extract()`
- `build_from_json()`
- `_rebuild_code()`
- `_read_text()`
- `_make_id()`
- `_file_stem()`
- `detect()`
- `main()`
- `ingest_scip_json()`
- `extract_js()`

## Concrete trace conclusions

1. `dispatch_command()` edges are real and branch-specific.
2. `extract()` fanout is huge and mostly real, not hallucinated.
3. `watch()` rebuild path is detect → reconcile → build → cluster → generate → export.
4. `serve.py` query/path/explain are distinct traversal/rendering paths.
5. `affected.py` is reverse-reachability over incoming edges.
6. `export.py` is the full output layer and contains the main safety guards.
7. `extractors/__init__.py` is registry-only; migration remains partial.

## Open drill points

If you want the trace fully exhausted, next reads are:

1. `kb_core/extract.py`
   - finish XAML, `_get_extractor`, `_extract_parallel`, `_extract_sequential`, `collect_files`

2. `kb_core/report.py`
   - final assembly of report sections

3. `kb_core/export.py`
   - the lower export helpers after `to_html`

4. per-language extractor modules still in `extractors/`
   - `julia.py`
   - `verilog.py`
   - `markdown.py`
   - `objc.py`
   - `pascal.py`
   - `csproj` / `slnx`-adjacent handlers in `extract.py`

5. `kb_core/analyze.py`
   - exact question-generation logic

Closed enough for now:

- extract routing
- question generation
- cache fingerprinting
- export safety
- query/path/explain routing

## Cache behavior

`kb_core/cache.py` fingerprints extraction prompts.

Key facts:

- prompt text is normalized before hashing
- CRLF and trailing whitespace do not change fingerprint
- fingerprinted cache lives under `cache/semantic/p{fingerprint}/`
- deep mode uses `cache/semantic-deep/`
- `check_semantic_cache()` can read by prompt text or prompt file
- `save_semantic_cache()` writes back into the same prompt namespace
- legacy flat cache entries are still supported

This is why the skill path cares about passing the exact prompt file path to cache-check and semantic extraction.

## Practical next questions

- Which edges in `extract()` are structural vs inferred?
- Which of the export formats are gated by size or missing dependencies?
- Where do ambiguous node names get resolved for query/path/explain?
- What exact logic decides whether `.h` is C, C++, or ObjC?
- Which semantic cache entries are prompt-stable vs prompt-invalidated?

## Note

This doc records trace state as of the current session. It is not a substitute for a full test run.
