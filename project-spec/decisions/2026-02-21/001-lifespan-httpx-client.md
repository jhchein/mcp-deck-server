# Decision: Use FastMCP lifespan for shared httpx client and config validation

**Date:** 2026-02-21
**Status:** Accepted

## Context

Currently, `make_nc_request` creates a new `httpx.AsyncClient` per call. This means no connection reuse, no HTTP keep-alive, and redundant SSL handshake overhead. Additionally, environment variables (`NC_URL`, `NC_USER`, `NC_APP_PASSWORD`) are resolved at module import time — if `.env` is absent (tests, linting), they silently bind to `None` and errors only surface at the first tool call.

## Decision

1. Use FastMCP's `lifespan` context manager to create a single shared `httpx.AsyncClient` with a default timeout (30s).
2. Resolve and validate all required environment variables inside the lifespan hook. Fail fast at startup if any are missing.
3. Inject the client and config into the MCP server context so tools can access them without module-level globals.

## Consequences

- Connection pooling and keep-alive across tool calls.
- Clear startup failure if config is incomplete.
- The httpx client becomes injectable, which unblocks test fixtures (mock client).
- Slight change to how tools access the client (via context rather than a module-level function).
