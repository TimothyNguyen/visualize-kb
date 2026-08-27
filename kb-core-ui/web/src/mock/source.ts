// Raw source text for the mock mini-repo, kept in sync line-for-line with the
// startLine/endLine ranges declared in ./data.ts.

export const MOCK_SOURCE: Record<string, string> = {
  "src/index.ts": `import { startServer } from "./server"

const CONFIG_PATH: string = "./config.json"

/**
 * main is the entrypoint for the KB Core demo service.
 */
function main(): void {
  const config = { port: 8080, host: "localhost" }
  startServer(config)
}

main()
`,
  "src/server.ts": `export interface Config {
  port: number
  host: string
}

export interface Handler {
  handleRequest(req: Request): Response
}

/**
 * startServer boots the HTTP router and begins listening for connections.
 */
export function startServer(config: Config): void {
  const router = new Router()
  router.handleRequest
}

export class Router implements Handler {
  /**
   * handleRequest dispatches an incoming request to the appropriate handler.
   */
  handleRequest(req: Request): Response {
    return new Response()
  }
}

export class AdminRouter extends Router {
}
`,
  "internal/models.go": `package internal

// DefaultTimeout is the maximum duration, in seconds, allowed for a single
// database query before it is cancelled.
const DefaultTimeout = 30

// User represents an application user record.
type User struct {
	Name  string
	Email string
}
`,
  "internal/service.go": `package internal

import "database/sql"

// FetchUser retrieves a user by ID from the database, using a short-lived
// connection from the pool.
func FetchUser(id string) (*User, error) {
	rows, err := queryDB("SELECT * FROM users WHERE id = ?")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanUser(rows)
}

// queryDB executes a raw SQL query against the primary connection pool.
func queryDB(query string) (*sql.Rows, error) {
	return db.Query(query)
}
`,
}

export function getMockSourceLines(filePath: string, start: number, end: number): string[] {
  const text = MOCK_SOURCE[filePath]
  if (!text) return []
  const allLines = text.replace(/\n$/, "").split("\n")
  // start/end are 1-indexed inclusive
  return allLines.slice(Math.max(0, start - 1), end)
}
