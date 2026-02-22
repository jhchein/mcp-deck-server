# Decision: Make `make_nc_request` raise on errors

**Date:** 2026-02-21
**Status:** Accepted

## Context

`make_nc_request` currently catches `httpx.HTTPStatusError` and `httpx.RequestError`, converts them into a `dict` with an `"error"` key, and returns it as the normal return value. Every tool then checks `isinstance(response, dict) and "error" in response` and re-raises as `ValueError`. This is repetitive, easy to forget, and invisible in the type signature (`-> Any`).

## Decision

1. `make_nc_request` should let `httpx.HTTPStatusError` propagate (or wrap it in a custom `DeckAPIError` exception).
2. Remove the error-dict return channel entirely.
3. Tool functions no longer need the `isinstance(..., dict) and "error"` guard — they handle only the success path.
4. Define a simple exception hierarchy:
   - `DeckAPIError(Exception)` — base for all Deck API errors.
   - `DeckHTTPError(DeckAPIError)` — wraps HTTP status errors with status code and response body.
   - `DeckConnectionError(DeckAPIError)` — wraps network/timeout errors.

## Consequences

- Tool functions become shorter and clearer (happy path only).
- Error handling is centralized in one place.
- FastMCP will surface exceptions to the MCP client as tool errors automatically.
- Custom exception types enable callers to catch specific failure modes if needed.
