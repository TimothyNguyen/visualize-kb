// Client for the workspace GraphRAG chat contract frozen under
// kb-core-ui/contracts/rag-chat/v1. The browser reaches FalkorDB and the LLM
// provider only through these endpoints; no credential or graph name is ever
// part of a request built here.

import { ApiRequestError, SERVICE_API_BASE } from "./client"
import type {
  ChatAnswer,
  ChatAskRequest,
  ChatCancelResult,
  ChatExplainGraphResponse,
  ChatFeedbackEntry,
  ChatFeedbackRating,
  ChatSourceMapResponse,
  ChatStreamEvent,
  ChatSuggestions,
  ChatTerminalEvent,
  ChatThread,
  ChatThreadDeleted,
  ChatThreadsDeleted,
} from "./types"

function chatBase(workspaceId: string): string {
  return `${SERVICE_API_BASE}/rag/workspaces/${encodeURIComponent(workspaceId)}/chat`
}

// Unlike serviceRequest, this surfaces the server's {"error": "..."} message.
// Those strings are the contract's own wording and carry no provider internals.
async function chatRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new ApiRequestError(response.status, body?.error || response.statusText)
  }
  return response.json() as Promise<T>
}

function postJson(body: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
}

export function askChat(workspaceId: string, request: ChatAskRequest): Promise<ChatAnswer> {
  return chatRequest(chatBase(workspaceId), postJson(request))
}

export function cancelChat(workspaceId: string, queryId: string): Promise<ChatCancelResult> {
  return chatRequest(`${chatBase(workspaceId)}/cancel`, postJson({ query_id: queryId }))
}

export function getChatSuggestions(workspaceId: string): Promise<ChatSuggestions> {
  return chatRequest(`${chatBase(workspaceId)}/suggestions`)
}

export function sendChatFeedback(
  workspaceId: string,
  queryId: string,
  rating: ChatFeedbackRating,
  comment = "",
): Promise<ChatFeedbackEntry> {
  return chatRequest(`${chatBase(workspaceId)}/feedback`, postJson({ query_id: queryId, rating, comment }))
}

export function getChatSourceMap(workspaceId: string, queryId: string): Promise<ChatSourceMapResponse> {
  return chatRequest(`${chatBase(workspaceId)}/source_map?query_id=${encodeURIComponent(queryId)}`)
}

export function getChatExplainGraph(workspaceId: string, queryId: string): Promise<ChatExplainGraphResponse> {
  return chatRequest(`${chatBase(workspaceId)}/explain_graph?query_id=${encodeURIComponent(queryId)}`)
}

export function getChatThread(workspaceId: string, threadId: string): Promise<ChatThread> {
  return chatRequest(`${chatBase(workspaceId)}/threads/${encodeURIComponent(threadId)}`)
}

export function deleteChatThread(workspaceId: string, threadId: string): Promise<ChatThreadDeleted> {
  return chatRequest(`${chatBase(workspaceId)}/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" })
}

export function deleteChatThreads(workspaceId: string): Promise<ChatThreadsDeleted> {
  return chatRequest(`${chatBase(workspaceId)}/threads`, { method: "DELETE" })
}

export function chatStreamUrl(workspaceId: string, request: ChatAskRequest): string {
  const params = new URLSearchParams({ query: request.query })
  if (request.thread_id) params.set("thread_id", request.thread_id)
  if (request.query_id) params.set("query_id", request.query_id)
  if (request.strategy) params.set("strategy", request.strategy)
  if (request.requested_k !== undefined) params.set("requested_k", String(request.requested_k))
  if (request.requested_graph_row_limit !== undefined) {
    params.set("requested_graph_row_limit", String(request.requested_graph_row_limit))
  }
  for (const sourceId of request.allowed_source_ids ?? []) params.append("allowed_source_ids", sourceId)
  return `${chatBase(workspaceId)}/stream?${params}`
}

export function isTerminalChatEvent(event: ChatStreamEvent): event is ChatTerminalEvent {
  return event.event === "completed" || event.event === "cancelled" || event.event === "error"
}

// Feeds raw response chunks in, gets whole SSE events out. Frames can straddle
// a chunk boundary, so the tail is held until its blank-line terminator lands.
export function createChatStreamParser(): (chunk: string) => ChatStreamEvent[] {
  let buffer = ""
  return (chunk: string) => {
    buffer += chunk
    const frames = buffer.split("\n\n")
    buffer = frames.pop() ?? ""
    const events: ChatStreamEvent[] = []
    for (const frame of frames) {
      let name = ""
      const data: string[] = []
      for (const line of frame.split("\n")) {
        // A comment line -- the heartbeat -- yields no event at all.
        if (line === "" || line.startsWith(":")) continue
        if (line.startsWith("event:")) name = line.slice("event:".length).trim()
        else if (line.startsWith("data:")) data.push(line.slice("data:".length).trim())
      }
      if (name && data.length > 0) {
        events.push({ event: name, data: JSON.parse(data.join("\n")) } as ChatStreamEvent)
      }
    }
    return events
  }
}

// Resolves with the stream's single terminal event. Aborting the signal closes
// the connection, which the server reads as a disconnect and cancels the query.
export async function streamChat(
  workspaceId: string,
  request: ChatAskRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<ChatTerminalEvent | undefined> {
  const response = await fetch(chatStreamUrl(workspaceId, request), { signal })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new ApiRequestError(response.status, body?.error || response.statusText)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  const parse = createChatStreamParser()
  let terminal: ChatTerminalEvent | undefined
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      for (const event of parse(decoder.decode(value, { stream: true }))) {
        onEvent(event)
        if (isTerminalChatEvent(event)) terminal = event
      }
    }
  } finally {
    reader.releaseLock()
  }
  return terminal
}
