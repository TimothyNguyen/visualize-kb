# T11 handoff (REST + SSE chat contract)

Branch: `rag-chatbot-manager`. Spec marker: `spec/rag-chatbot-manager-SPEC.md` T11 currently `~` (in progress, not yet `x`).

## Done this session

- **Heartbeats**: SSE keep-alives now sent as comment frames (`: heartbeat\n\n`), not a named event — cannot be mistaken for content. `wire.py::SSE_HEARTBEAT_FRAME`, `chat_manager.py` emits `SSE_EVENT_HEARTBEAT` every 5 polls in `open_stream`, `app.py::_handle_chat` frames it as the raw comment.
- **Contract dedup**: `chat_contract_payload` now takes the workflow's JSON dict (not a `ChatResponse`), drops duplicate `evidence` key, keeps `context` as canonical field. `list_thread` replays turns through the same function — live and replayed answers are one shape.
- **Frozen fixtures**: `kb-core-ui/contracts/rag-chat/v1/` (6 files: `chat_complete.json`, `chat_thread.json`, `chat_stream.sse`, `chat_stream_cancelled.sse`, `chat_stream_error.sse`, `errors.json`) regenerated + byte-compared by `kb-core-ui/python/tests/test_rag_chat_contract_fixtures.py`. Fixed CRLF vs LF drift (fixtures now forced LF via `kb-core-ui/contracts/.gitattributes`, Python reader uses `newline=""`).
- **TypeScript client**: `kb-core-ui/web/src/api/types.ts` has full wire-type section (`ChatAnswer`, `ChatAskRequest`, `ChatStreamEvent` union, etc). New `kb-core-ui/web/src/api/chat.ts`: `askChat`, `cancelChat`, `getChatSuggestions`, `sendChatFeedback`, `getChatSourceMap`, `getChatExplainGraph`, `getChatThread`, `deleteChatThread(s)`, `chatStreamUrl`, `createChatStreamParser`, `streamChat`. `client.ts` now exports `SERVICE_API_BASE`.
- **Web test**: `kb-core-ui/web/src/api/chat.test.ts` — 17 tests, reads frozen fixtures off disk (not imported, avoids Vite `?url` denial), all green.
- Python: `tests/test_rag_chat_manager.py`, `test_rag_chat_http.py`, `test_rag_chat_contract_fixtures.py` — 52 passed last full run.

## NOT done yet — pick up here

1. **Harness stage** (`kb-core-ui/harness/harness/rag_workflow.py`): add `chat_http_contract` stage exercising **real HTTP transport** (`listen_and_serve` in a thread + `urllib`, not just calling `ChatManager` methods directly). Insert into `REQUIRED_STAGES` tuple (after `"chat_persistence"`) AND the `stages` tuple inside `execute_rag_workflow`. `kb-core-ui/harness/tests/test_rag_workflow.py:23` asserts report stage names == `list(REQUIRED_STAGES)` — must update alongside.
2. Run harness fake backend: `cd kb-core-ui/harness && ..\..\.venv-ui\Scripts\python.exe -m pytest -q` then `... -m harness rag --backend fake --report .harness-work/rag/fake.json`.
3. If FalkorDB-facing behavior changed (it didn't this session, but verify), run pinned `falkordb/falkordb:v4.20.4` backend too.
4. Full regressions: `cd kb-core-ui/python && python -m pytest -q`; `cd kb-core-ui/web && pnpm test && pnpm lint && pnpm build` (scripts: `vitest run`, `oxlint`, `tsc -b && vite build`).
5. Flip T11 `~` → `x` in `spec/rag-chatbot-manager-SPEC.md`.
6. Append a "## T11 result" section to `docs/CLAUDE-RAG-HANDOFF.md` (test counts, new required-stage count) — mirror T9/T10 sections there.
7. `git status --short` + `git diff --check`, commit T11 **separately** (not combined with other tasks). Do **not** push unless asked.

## Invariants (must hold)

Browser never touches FalkorDB/provider APIs directly. Every read/write workspace-scoped server-side. User values never become raw Cypher/labels/props. Secrets never in payloads/logs/fixtures (checked: `FIXTURE_PASSWORD`, `falkor://` absent from all fixtures). Frontend talks only to the T11 REST/SSE contract — no FalkorDB URL/creds in Vite env.

Full non-negotiable workflow steps are in `docs/CLAUDE-RAG-HANDOFF.md` under T11's original spec row + `spec/rag-chatbot-manager-SPEC.md`.
