"""Minimal AG-UI bridge over the frozen workspace chat contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from uuid import uuid4

from kb_core_ui import jsonx
from kb_core_ui.rag.chat_contract import (
    SSE_EVENT_CANCELLED,
    SSE_EVENT_COMPLETED,
    SSE_EVENT_ERROR,
    SSE_EVENT_HEARTBEAT,
    SSE_EVENT_QUEUED,
    SSE_EVENT_TOKEN,
)


class AgUiError(ValueError):
    pass


@dataclass(frozen=True)
class AgUiRun:
    workspace_id: str
    thread_id: str
    run_id: str
    query: str
    strategy: str
    allowed_source_ids: tuple[str, ...]


def parse_run_input(value: Mapping[str, Any]) -> AgUiRun:
    state = value.get("state")
    if not isinstance(state, Mapping):
        state = {}
    workspace_id = _string(state, "workspace_id") or _string(state, "workspaceId")
    if not workspace_id:
        raise AgUiError("AG-UI state.workspace_id is required")
    thread_id = _string(value, "threadId") or _string(value, "thread_id") or uuid4().hex
    run_id = _string(value, "runId") or _string(value, "run_id") or uuid4().hex
    query = _last_user_text(value.get("messages"))
    if not query:
        raise AgUiError("AG-UI input requires a user text message")
    strategy = _string(state, "strategy") or "auto"
    sources = state.get("allowed_source_ids", state.get("allowedSourceIds", ()))
    allowed_source_ids = tuple(item for item in sources if isinstance(item, str)) if isinstance(sources, list) else ()
    return AgUiRun(
        workspace_id=workspace_id,
        thread_id=thread_id,
        run_id=run_id,
        query=query,
        strategy=strategy,
        allowed_source_ids=allowed_source_ids,
    )


def agui_stream(chat_manager: Any, run: AgUiRun) -> Iterable[bytes]:
    message_id = f"message-{run.run_id}"
    text_started = False
    domain_events = chat_manager.open_stream(
        run.workspace_id,
        query=run.query,
        thread_id=run.thread_id,
        allowed_source_ids=run.allowed_source_ids,
        strategy=run.strategy,
        query_id=run.run_id,
    )
    for event, data in domain_events():
        if event == SSE_EVENT_HEARTBEAT:
            yield b": heartbeat\n\n"
        elif event == SSE_EVENT_QUEUED:
            yield _event("RUN_STARTED", threadId=run.thread_id, runId=run.run_id)
        elif event == SSE_EVENT_TOKEN:
            if not text_started:
                yield _event(
                    "TEXT_MESSAGE_START", messageId=message_id, role="assistant"
                )
                text_started = True
            yield _event(
                "TEXT_MESSAGE_CONTENT", messageId=message_id, delta=str(data.get("text", ""))
            )
        elif event == SSE_EVENT_COMPLETED:
            if text_started:
                yield _event("TEXT_MESSAGE_END", messageId=message_id)
            # AG-UI snapshots replace, rather than merge, client state. Keep the
            # workspace scope so a second turn cannot lose its authorization boundary.
            yield _event(
                "STATE_SNAPSHOT",
                snapshot={
                    "workspace_id": run.workspace_id,
                    "strategy": run.strategy,
                    "allowed_source_ids": list(run.allowed_source_ids),
                    "last_answer": data,
                },
            )
            yield _event(
                "RUN_FINISHED", threadId=run.thread_id, runId=run.run_id, result=data
            )
        elif event == SSE_EVENT_CANCELLED:
            yield _event("RUN_ERROR", message="Query cancelled", code="cancelled")
        elif event == SSE_EVENT_ERROR:
            yield _event(
                "RUN_ERROR",
                message=str(data.get("message", "Chat request failed")),
                code=str(data.get("status", "chat_error")),
            )


def _event(event_type: str, **payload: Any) -> bytes:
    data = jsonx.dumps({"type": event_type, **payload})
    return f"data: {data}\n\n".encode("utf-8")


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    return item if isinstance(item, str) else ""


def _last_user_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, Mapping) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, Mapping) and item.get("type") in {"text", "input_text"}
            ]
            return "".join(parts).strip()
    return ""
