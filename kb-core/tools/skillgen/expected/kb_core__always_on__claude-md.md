## kb-core

This project has a knowledge graph at kb-core-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `kb-core query "<question>"` when kb-core-out/graph.json exists. Use `kb-core path "<A>" "<B>"` for relationships and `kb-core explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If kb-core-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read kb-core-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `kb-core update .` to keep the graph current (AST-only, no API cost).
