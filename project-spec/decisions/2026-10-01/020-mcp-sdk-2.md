# Decision 020 — Move to the MCP Python SDK 2.x

**Date:** 2026-10-01
**Status:** Accepted
**Delivery:** One PR.

## Context

The MCP Python SDK 2.0 was released as stable and `pip install mcp` now installs 2.x. The 1.x line is in maintenance mode and receives security fixes only. Until now `pyproject.toml` capped the SDK at `<2` (a `constraint-dependencies` entry plus the dependency itself), because 2.x removes the `mcp.server.fastmcp` module this server imports, and Dependabot kept proposing a bump that the cap made unresolvable.

An experiment on a branch showed that the server runs on 2.2.0 with a small port. The 2.x protocol era (stateless requests, `server/discover`) is served by the SDK itself and needs no code here.

## Decision

Require `mcp>=2.2,<3` and port the server:

- `FastMCP` becomes `MCPServer`; `ToolError` is imported from `mcp.server.mcpserver.exceptions`.
- Tool annotations use the snake_case fields (`read_only_hint`, …).
- `MCPServer.get_context()` no longer exists. The lifespan publishes its `DeckRuntime` in a module variable and `get_runtime()` reads it. The tools take no `ctx` parameter, so their signatures and the schema the agent sees stay unchanged. The server is a process-wide singleton, so one active runtime is enough; nested lifespans (tests) restore the previous one.
- **Error text reaches the agent only through `ToolError`.** 2.x masks any other exception as `Error executing tool <name>`. Our `DeckAPIError` and `ValueError` messages are written for the agent (status, hint, what to change), so the tool wrapper re-raises them as `ToolError`. Without this, a 401 hint, a read-only refusal or a deadline message would not arrive. Unexpected exceptions stay masked, which is the SDK's intent. `DeckTimeoutError` is removed; the deadline raises `ToolError` directly.
- `call_tool` returns a `CallToolResult`; the test helper reads `.content` and asserts `structured_content is None`.

## Rejected alternatives

- **Support 1.x and 2.x at once.** Needs import shims for the module move, the `get_context` removal and the field renames, and doubles the CI matrix for a single-user server. 1.x only gets security fixes.
- **Add a `ctx: Context` parameter to every tool.** It is the SDK's intended pattern, but it changes 14 signatures and the wrapper has to forward it, for no gain over a singleton runtime.
- **Stay on 1.x with the cap.** Viable for now, but it leaves Dependabot noise and defers the port until 1.x stops getting fixes.

## Consequences

- `httpx-sse` and `pydantic-settings` leave the lock file; `httpx2`, `mcp-types`, `opentelemetry-api` and `truststore` join it. Our own HTTP client still uses `httpx`.
- OpenTelemetry tracing is on by default in the SDK. It needs an exporter to send anything; this server configures none.
- `serverInfo.version` is empty unless set; the server reports the name `deck` as before.
- Clients keep working: 2.x serves every earlier protocol revision.
