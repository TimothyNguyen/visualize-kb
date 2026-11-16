import { createServer } from "node:http"

const host = process.env.COPILOTKIT_HOST ?? "127.0.0.1"
const port = Number(process.env.COPILOTKIT_PORT ?? "3001")
const agentUrl = process.env.KB_CORE_AGENT_URL ?? "http://127.0.0.1:8420/api/rag/agent"

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("COPILOTKIT_PORT must be an integer between 1 and 65535")
}

const parsedAgentUrl = new URL(agentUrl)
if (!['http:', 'https:'].includes(parsedAgentUrl.protocol)) {
  throw new Error("KB_CORE_AGENT_URL must use http or https")
}

// Set before importing CopilotKit. Internal-code mode sends no telemetry.
process.env.COPILOTKIT_TELEMETRY_DISABLED = "true"

const [{ HttpAgent }, { CopilotRuntime }, { createCopilotNodeListener }] = await Promise.all([
  import("@ag-ui/client"),
  import("@copilotkit/runtime/v2"),
  import("@copilotkit/runtime/v2/node"),
])

const runtime = new CopilotRuntime({
  agents: {
    "kb-core": new HttpAgent({ url: parsedAgentUrl.toString() }),
  },
})
const copilotListener = createCopilotNodeListener({
  runtime,
  basePath: "/api/copilotkit",
  activateChannels: false,
})

const server = createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json; charset=utf-8" })
    response.end('{"status":"ok"}\n')
    return
  }
  void copilotListener(request, response).catch(() => {
    if (!response.headersSent) {
      response.writeHead(502, { "content-type": "application/json; charset=utf-8" })
    }
    response.end('{"error":"Copilot runtime request failed"}\n')
  })
})

server.listen(port, host, () => {
  process.stdout.write(`CopilotKit runtime listening on http://${host}:${port}\n`)
})

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => server.close(() => process.exit(0)))
}
