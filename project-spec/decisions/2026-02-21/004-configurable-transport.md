# Decision: Make transport configurable (stdio / sse)

**Date:** 2026-02-21
**Status:** Accepted

## Context

The server currently hardcodes `mcp.run(transport="stdio")`. The project goals include supporting remote SSE/HTTP transport for hosting scenarios beyond local MCP clients.

## Decision

1. Read transport mode from `MCP_TRANSPORT` environment variable, defaulting to `"stdio"`.
2. Valid values: `"stdio"`, `"sse"`.
3. Fail fast with a clear error if an unrecognized transport value is provided.
4. For SSE mode, FastMCP handles the HTTP server internally — no additional web framework needed.

## Consequences

- Local and remote operation from the same codebase, controlled by a single env var.
- No code changes needed to switch between modes — configuration only.
- SSE mode will expose an HTTP endpoint; security constraints (auth, network binding) should be addressed before deploying remotely.
