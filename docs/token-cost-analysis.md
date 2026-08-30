# Token Cost Instrumentation — Current State vs. Target

## Current state

- `estimate_cost(backend, input_tokens, output_tokens)` — `kb_core/llm.py:3021` (verified) — returns a USD estimate from published per-backend pricing.
- Call sites: `cli.py:4080` and `cli.py:4266` (both verified).
  - At `cli.py:4266-4288` (verified), the `extract` command's cost estimate is computed **after** extraction and only **printed to stdout** (`[kb-core extract] tokens: ... est. cost (~{backend}): ${cost:.4f}`) — it is not persisted anywhere.
  - The actual token counts (`input_tokens`, `output_tokens`) ARE persisted, but into the extraction's `analysis.json` under `"tokens": {"input": ..., "output": ...}` (`cli.py:4253-4256`, verified) — a flat aggregate for the whole extraction run, not per-query, per-category, or per-conversation-turn.
- `"cost.json"` is listed in `export.py:32`'s `_BACKUP_ARTIFACTS` (a set of filenames the pre-overwrite backup mechanism watches for if present) — but no writer for a file literally named `cost.json` was found in `kb_core/` in this pass. Treat it as an aspirational/legacy artifact name, not a working instrumentation path, unless a writer turns up in `kb-core-ui` or generated skill scripts (outside this audit's scope).
- No per-query cost tracking exists — `serve.py`'s query/path/explain functions don't call `estimate_cost` at all; cost tracking today is scoped to the `extract` (indexing) LLM calls, not to query-time or chat LLM calls in `kb-core-ui`.

## Gap vs. target (mission §17)

The mission spec asks for a breakdown by category: system-prompt tokens, conversation-history tokens, graph-context tokens, document-context tokens, memory tokens, tool-schema tokens, cache hit/miss, latency, cost — per operation.

Today's instrumentation is **aggregate-only, extraction-scoped**: one input/output token count per `extract` run, no breakdown, no query-time or chat-time tracking at all.

## Target (design, not implementation this round)

1. Extend `estimate_cost` call sites to tag each call with an `operation` label (`extract`, `query`, `chat`) rather than adding new cost logic — reuse the existing function.
2. At the `kb-core-ui` chat/bot layer (`bots/common.py`), wrap each LLM call with a token-category breakdown (system prompt vs. history vs. graph-context vs. memory) before calling `estimate_cost`, and persist the breakdown per `QueryRun`/turn (see `memory-model.md` for the `QueryRun` entity) rather than only printing an aggregate.
3. Resolve the `cost.json` naming question before building anything against it: either implement a real writer at that path (if the name is meant to be canonical) or remove it from `_BACKUP_ARTIFACTS` (if it's dead).
4. Do not introduce a new cost-tracking subsystem — extend the existing `estimate_cost` + `analysis.json`/per-turn-persistence pattern already in place.
