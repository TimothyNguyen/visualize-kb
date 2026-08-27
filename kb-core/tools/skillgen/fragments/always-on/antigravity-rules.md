---
trigger: always_on
description: Consult the kb-core knowledge graph at kb-core-out/ for codebase and architecture questions.
---

## kb-core

This project has a kb-core knowledge graph at kb-core-out/.

Rules:
- For codebase or architecture questions, when `kb-core-out/graph.json` exists, first run `kb-core query "<question>"` (CLI) or `query_graph` (MCP). Use `kb-core path "<A>" "<B>"` / `shortest_path` for relationships and `kb-core explain "<concept>"` / `get_node` for focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- If kb-core-out/wiki/index.md exists, navigate it instead of reading raw files
- Read kb-core-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- After modifying code files in this session, run `kb-core update .` to keep the graph current (AST-only, no API cost)
