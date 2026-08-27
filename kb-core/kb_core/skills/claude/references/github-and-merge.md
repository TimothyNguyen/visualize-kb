# kb-core reference: GitHub clone and cross-repo merge

Load this when the user passed one or more `https://github.com/...` URLs, or named several local subfolders to merge into one graph.

### Step 0 - Clone GitHub repo(s) (only if a GitHub URL was given)

**Single repo:**
```bash
LOCAL_PATH=$(kb-core clone <github-url> [--branch <branch>])
# Use LOCAL_PATH as the target for all subsequent steps
```

**Multiple repos (cross-repo graph):**
```bash
# Clone each repo, run the full pipeline on each, then merge
kb-core clone <url1>   # → ~/.kb_core/repos/<owner1>/<repo1>
kb-core clone <url2>   # → ~/.kb_core/repos/<owner2>/<repo2>
# Run /kb-core on each local path to produce their graph.json files
# Then merge:
kb-core merge-graphs \
  ~/.kb_core/repos/<owner1>/<repo1>/kb-core-out/graph.json \
  ~/.kb_core/repos/<owner2>/<repo2>/kb-core-out/graph.json \
  --out kb-core-out/cross-repo-graph.json
```

KB Core clones into `~/.kb_core/repos/<owner>/<repo>` and reuses existing clones on repeat runs. Each node in the merged graph carries a `repo` attribute so you can filter by origin.

**Multiple local subfolders (monorepo or multi-service layout):**

The skill pipeline writes all intermediate and final outputs to `kb-core-out/` in the current working directory. Running the skill on each subfolder separately will clobber the same output dir. Instead, use the CLI directly for each subfolder — it places `kb-core-out/` *inside* the scanned path:

```bash
kb-core extract ./core/     # → ./core/kb-core-out/graph.json
kb-core extract ./service/  # → ./service/kb-core-out/graph.json
kb-core extract ./platform/ # → ./platform/kb-core-out/graph.json
# Add --backend gemini|kimi|openai|deepseek|claude-cli depending on which API key you have set

# Then merge at the project root:
kb-core merge-graphs \
  ./core/kb-core-out/graph.json \
  ./service/kb-core-out/graph.json \
  ./platform/kb-core-out/graph.json \
  --out kb-core-out/graph.json
```

Once `kb-core-out/graph.json` exists, the fast path above takes over: any codebase question runs `kb-core query` directly on the merged graph — no re-extraction, no size gate.
