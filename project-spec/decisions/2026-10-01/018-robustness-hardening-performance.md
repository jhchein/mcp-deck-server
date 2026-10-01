# Decision 018 — Robustness, Hardening and Performance Pass

**Date:** 2026-10-01
**Status:** Accepted
**Delivery:** Three stacked PRs — (1) robustness, (2) security hardening, (3) performance and agent ergonomics.

## Context

An implementation review of the server found no blocking defects, but three gaps that matter because the only consumer is an LLM agent:

1. **Errors are opaque.** `DeckHTTPError` carried the response body as an attribute, but FastMCP surfaces only `str(error)`, so the agent saw `Deck API HTTP error 400` without Deck's reason (for example `title must be provided`) and could not self-correct. Transient failures (429, 502-504, connect timeouts) failed the whole tool call, and a 200 response with a non-JSON body raised a bare `JSONDecodeError`.
2. **Writes are unrestricted.** A Nextcloud app password is an account credential (`docs/security.md`). Card titles and descriptions are untrusted text that the agent reads and then acts on, so prompt injection can reach every write tool. Tools carry no MCP annotations, and `http://` URLs send Basic auth in clear text.
3. **Avoidable cost.** `get_assigned_cards` scans boards sequentially. Both tools return full 23-field cards, which burns agent context.

Latency itself is acceptable (`docs/performance.md`), so the order of work is robustness, then hardening, then performance.

## Decision

### Phase 1 — Robustness

- `DeckHTTPError` messages include Deck's `message` field, whitespace-collapsed and truncated to 300 characters. Non-JSON bodies (HTML error pages) are never echoed.
- A non-JSON success body raises `DeckResponseError(DeckAPIError)` instead of a raw `JSONDecodeError`.
- `GET` requests retry transient failures (HTTP 429/502/503/504 and transport errors) with exponential backoff, honouring `Retry-After` up to a cap. Retries are configurable via `MCP_MAX_RETRIES` (default 2, 0 disables). Writes are never retried because a lost response could duplicate a mutation.
- `get_assigned_cards` returns `AssignedCards` (`cards`, `skipped_boards`). A board answering 403 or 404 is skipped and reported instead of failing the whole scan. Other errors still propagate.
- `move_card` no longer rewrites order `0` to `999`, and no longer silently picks the last of several stacks that share a name. It raises with the candidate IDs, and a new optional `target_stack_id` disambiguates.
- `update_card` keeps order `0`. The read-then-write race stays: the Deck API offers no conditional PUT, so the docstring documents it.
- The `mcp-server` shim package is replaced by a direct dependency on `mcp`, which the code already imports. `pydantic` is declared directly.

### Phase 2 — Security hardening

- `MCP_READ_ONLY=true` hides every write tool from the MCP tool list. This is the main control, because the app password cannot be scoped to Deck.
- Every tool carries MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) so clients can prompt before risky calls.
- `NC_URL` must use `https` unless the host is loopback or `NC_ALLOW_INSECURE_HTTP=true` is set.
- `NC_API_VERSION` must match `v<major>(.<minor>)?` because it is interpolated into the URL path.
- Title and description lengths are capped.
- Write tools log one audit line to stderr (tool name and IDs, never content or credentials). stdout stays reserved for the MCP protocol.

### Phase 3 — Performance and ergonomics

- `get_assigned_cards` fetches boards concurrently, bounded by a semaphore of 5.
- `list_cards` and `get_assigned_cards` accept `compact=true` and then return `CardSummary` objects with the fields an agent normally needs.

## Rejected alternatives

- **`list_cards` via `GET /boards/{board}/stacks/{stack}`.** The initial review proposed this to avoid downloading every stack. A live check against a Nextcloud instance showed the single-stack endpoint returns degraded cards: `labels` is `null` and `owner` is a plain string instead of an object, while the stack list returns both. Switching would silently drop labels, so `list_cards` keeps reading the stack list.
- **Retry writes with idempotency keys.** Deck has no idempotency support, so a retry could create duplicate cards.
- **Response caching.** Stacks expose no ETag and Deck sends `no-store`, so cached data would risk stale agent output (decision 011).
- **Tool allowlist environment variable.** Read-only mode covers the real risk with less configuration. An allowlist can follow if users ask.
- **Optimistic locking in `update_card`.** Re-checking `lastModified` before the PUT narrows the race but cannot close it, and adds a request to every update.
- **Restricting the `owner` argument of `update_card`.** The owner payload shape is undocumented (decisions 013 and 016), so a stricter schema would guess at it.
- **New feature tools (comments, upcoming cards, unarchive).** Deferred. They need their own decisions, especially comments, which use the OCS base URL and pagination.

## Consequences

- `get_assigned_cards` changes its return shape. Agents read `cards` instead of a bare list. This is a breaking change for any script consuming the tool output.
- A new optional parameter on `move_card` and new optional environment variables. Defaults preserve current behaviour, except that plain `http://` non-loopback URLs now fail at startup.
- Read-only mode changes which tools are listed, so clients need a restart to pick up a change.
- Retries can lengthen the worst-case tool call to roughly `(MCP_MAX_RETRIES + 1) × MCP_REQUEST_TIMEOUT`.
