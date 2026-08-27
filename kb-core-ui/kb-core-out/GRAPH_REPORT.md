# Graph Report - kb-core-ui  (2026-08-27)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 665 nodes · 1546 edges · 33 communities (26 shown, 7 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 148 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e0ced6af`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `kb-core update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 31

## God Nodes (most connected - your core abstractions)
1. `Store` - 24 edges
2. `compilerOptions` - 18 edges
3. `Kind` - 18 edges
4. `writeJSON()` - 18 edges
5. `Store` - 17 edges
6. `New()` - 17 edges
7. `Open()` - 16 edges
8. `FileGraph` - 16 edges
9. `ParseGo()` - 16 edges
10. `nodeText()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `newServeCmd()` --calls--> `NewRunner()`  [EXTRACTED]
  cmd/kb-core-ui/serve.go → internal/bots/runner.go
- `newBotGraphSyncCmd()` --calls--> `Open()`  [EXTRACTED]
  cmd/kb-core-ui/bot_graphsync.go → internal/store/store.go
- `openStoreAndIndex()` --calls--> `Open()`  [EXTRACTED]
  cmd/kb-core-ui/common.go → internal/store/store.go
- `openMemory()` --calls--> `EmbedderFromEnv()`  [EXTRACTED]
  cmd/kb-core-ui/memory.go → internal/memory/neural.go
- `openMemory()` --references--> `Store`  [EXTRACTED]
  cmd/kb-core-ui/memory.go → internal/memory/store.go

## Import Cycles
- None detected.

## Communities (33 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (60): ArgDef, Def, ErrMissingArg, ErrUnknownBot, lockedWriter, Run, RunSummary, bytes.Buffer (+52 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (44): github.com/smacker/go-tree-sitter.Language, github.com/smacker/go-tree-sitter.Node, github.com/smacker/go-tree-sitter.Point, FileGraph, Param, Symbol, UnresolvedCall, goFunc() (+36 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (34): net/http.Client, time.Time, add(), charTrigrams(), Cosine(), NewHashingEmbedder(), stem(), tokenize() (+26 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (42): @dagrejs/dagre, oxlint, react, react-dom, react-router-dom, oxc, warn, @types/node (+34 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (33): newBotGraphSyncCmd(), printHealth(), hasRepoFlag(), locateBotsDir(), newBotCmd(), newBotDoctorCmd(), newBotPassthroughCmd(), newBotPRReviewCmd() (+25 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (25): getFileSymbols(), getSymbol(), getSymbolCallers(), getSymbolCalls(), loadGraph(), CallEdgeEntry, Symbol, SymbolKind (+17 more)

### Community 6 - "Community 6"
Cohesion: 0.18
Nodes (16): net/http.Handler, net/http.HandlerFunc, net/http.Request, net/http.ResponseWriter, net/http.ServeMux, Server, Server, validMemKind() (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.13
Nodes (22): EdgeKind, Graph, BuildFlat(), dirOf(), languageFamily(), resolveCall(), resolveParents(), Edge (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (23): database/sql.DB, database/sql.Tx, github.com/mark3labs/mcp-go/mcp.CallToolResult, github.com/mark3labs/mcp-go/server.MCPServer, github.com/mark3labs/mcp-go/server.ToolHandlerFunc, getCalleesHandler(), getCallersHandler(), getFileSliceHandler() (+15 more)

### Community 9 - "Community 9"
Cohesion: 0.13
Nodes (25): addMemory(), ApiRequestError, deleteMemory(), getBotRuns(), getBots(), getMemory(), KbCoreEdge, KbCoreGraph (+17 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (23): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+15 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (19): ADMIN_ROUTER_CLASS, ALL_EDGES, ALL_SYMBOLS, CONFIG_IFACE, CONFIG_PATH, DEFAULT_TIMEOUT, FETCH_USER, HANDLER_IFACE (+11 more)

### Community 12 - "Community 12"
Cohesion: 0.18
Nodes (15): build_mcp_config(), ensure_indexed(), extract_json(), find_kb_core_ui_bin(), gh(), preflight_or_exit(), CompletedProcess, Path (+7 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (19): node, vite.config.ts, compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection (+11 more)

### Community 14 - "Community 14"
Cohesion: 0.20
Nodes (14): EdgeKind, dirOf(), GlobalGraph(), nodeTypes, EDGE_KINDS, GraphLegend(), layoutWithDagre(), EDGE_COLOR_VAR (+6 more)

### Community 15 - "Community 15"
Cohesion: 0.21
Nodes (15): byId(), callEntries(), edgeKind(), getGraph(), getSubgraph(), getSymbolMembers(), lineNumber(), search() (+7 more)

### Community 16 - "Community 16"
Cohesion: 0.17
Nodes (12): getSource(), ApiError, BotArg, BotDef, BotRun, BotRunSummary, Param, RunStatus (+4 more)

### Community 17 - "Community 17"
Cohesion: 0.29
Nodes (15): Check, check_claude_auth(), check_claude_installed(), check_claude_mcp(), check_gh_auth(), check_gh_installed(), check_python(), find_kb_core_ui_bin() (+7 more)

### Community 18 - "Community 18"
Cohesion: 0.20
Nodes (9): react, getStats(), StatsResponse, App(), Header(), CommandPalette(), onKeyDown(), select() (+1 more)

### Community 19 - "Community 19"
Cohesion: 0.39
Nodes (11): build_mcp_config(), ensure_indexed(), extract_findings(), find_kb_core_ui_bin(), format_comment(), gh(), main(), CompletedProcess (+3 more)

### Community 20 - "Community 20"
Cohesion: 0.28
Nodes (8): getTree(), language(), toSymbol(), TreeNode, LanguageBadge(), FileTree(), TreeEntry(), languageIcon()

### Community 21 - "Community 21"
Cohesion: 0.39
Nodes (8): getBotRun(), BotsView(), handleRunClick(), selectRun(), startRun(), submitForm(), toggleForm(), shortTime()

## Knowledge Gaps
- **101 isolated node(s):** `ApiError`, `BotArg`, `Param`, `ImportMeta`, `ImportMetaEnv` (+96 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `kb-core query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Store` connect `Community 8` to `Community 0`, `Community 4`, `Community 6`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `react` connect `Community 18` to `Community 3`, `Community 5`, `Community 9`, `Community 14`, `Community 15`, `Community 16`, `Community 20`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `plugins` connect `Community 3` to `Community 18`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **What connects `ApiError`, `BotArg`, `Param` to the rest of the system?**
  _101 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.056962025316455694 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1380392156862745 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.0784313725490196 - nodes in this community are weakly interconnected._