# kb-core reference: extra exports and benchmark

Load this when the user passed one of the export flags (`--wiki`, `--neo4j`, `--neo4j-push`, `--falkordb`, `--falkordb-push`, `--svg`, `--graphml`, `--mcp`), or when the corpus is large enough for the token-reduction benchmark. Each step runs only for its own flag.

### Step 6b - Wiki (only if --wiki flag)

**Only run this step if `--wiki` was explicitly given in the original command.**

Run this before Step 9 (cleanup) so `.kb_core_labels.json` is still available.

```bash
kb-core export wiki
```

### Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag)

**If `--neo4j`** - generate a Cypher file for manual import:

```bash
kb-core export neo4j
```

**If `--neo4j-push <uri>`** - push directly to a running Neo4j instance. Ask the user for credentials if not provided:

```bash
kb-core export neo4j --push bolt://localhost:7687 --user neo4j --password PASSWORD
```

Default URI is `bolt://localhost:7687`, default user is `neo4j`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag)

**If `--falkordb`** - generate a Cypher file. The statements are OpenCypher, but FalkorDB's `GRAPH.QUERY` runs one statement at a time (no bulk script import like Neo4j's `cypher-shell`), so prefer `--falkordb-push` to load a graph. Use this only when you want the portable `cypher.txt` artifact:

```bash
kb-core export falkordb
```

**If `--falkordb-push <uri>`** - push directly to a running FalkorDB instance. Credentials are optional; ask the user only if the instance requires auth:

```bash
kb-core export falkordb --push falkordb://localhost:6379
```

Default URI is `falkordb://localhost:6379` (the scheme is informational - `redis://` or a bare `host:port` work too), auth is optional, and the target graph defaults to `kb-core`. Uses MERGE - safe to re-run without creating duplicates.

### Step 7b - SVG export (only if --svg flag)

```bash
kb-core export svg
```

### Step 7c - GraphML export (only if --graphml flag)

```bash
kb-core export graphml
```

### Step 7d - MCP server (only if --mcp flag)

```bash
$(cat kb-core-out/.kb_core_python) -m kb_core.serve kb-core-out/graph.json
```

This starts a stdio MCP server that exposes tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`. Add to Claude Desktop or any MCP-compatible agent orchestrator so other agents can query the graph live.

To configure in Claude Desktop, add to `claude_desktop_config.json`. Claude Desktop can't run `$(...)`, and under `uv tool install` the system `python3` can't import kb_core — so set `command` to the **absolute interpreter path** printed by `cat kb-core-out/.kb_core_python`:
```json
{
  "mcpServers": {
    "kb-core": {
      "command": "<absolute path from: cat kb-core-out/.kb_core_python>",
      "args": ["-m", "kb_core.serve", "/absolute/path/to$kb-core-out/graph.json"]
    }
  }
}
```

### Step 8 - Token reduction benchmark (only if total_words > 5000)

If `total_words` from `kb-core-out/.kb_core_detect.json` is greater than 5,000, run:

```bash
kb-core benchmark
```

Print the output directly in chat. If `total_words <= 5000`, skip silently - the graph value is structural clarity, not token compression, for small corpora.
