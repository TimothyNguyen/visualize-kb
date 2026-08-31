# GraphRAG demo workspace

This workspace is seeded by the local Docker Compose stack so a fresh clone has
something to chat about before any real repository is ingested.

## Workspaces

A workspace groups repositories and documents. Each workspace owns one FalkorDB
graph, and every read and write is scoped to that workspace on the server. A
source is owned by exactly one workspace, so deleting a source removes only the
records that source published.

## Ingestion

Ingestion normalizes a source into a versioned envelope, stages it, reconciles
it against the workspace graph, and deletes the stale records that source
previously owned. Runs report counts and rejections instead of failing silently.

## Retrieval

Chat answers come from hybrid retrieval over chunk embeddings plus a bounded
traversal of the workspace graph. Every answer carries citations pointing back
at the source location the evidence came from.

## Mocked mode

The compose stack defaults to a deterministic fake model and a hashing embedder,
so the demo runs with no provider account and no API key. Answers are stable
across runs, which is what makes them usable in tests.
