---
inclusion: always
---

kb-core: A knowledge graph of this project lives in `kb-core-out/`. For codebase, architecture, or dependency questions, when `kb-core-out/graph.json` exists, first run `kb-core query "<question>"` (or `kb-core path "<A>" "<B>"` / `kb-core explain "<concept>"`). These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output. Read `GRAPH_REPORT.md` only for broad architecture review or when those commands do not surface enough context.
