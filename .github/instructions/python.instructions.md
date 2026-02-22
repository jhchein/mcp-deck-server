---
applyTo: "**/*.py"
---

# Python — mcp-deck-server conventions

## Package Structure

- `mcp_deck_server/` is the package root (flat at repo root, not `src/` layout).
- `config.py` and `models.py` are leaf modules — they must not import from other project modules.
- `client.py` depends on `config` and `models` only.
- `server.py` is the composition root — it wires FastMCP, lifespan, tools, client, and config.
- `main.py` is a thin entrypoint that imports and runs the server.

## MCP Tools

- Register tools with `@mcp.tool()` in `server.py`.
- All tool functions are `async`.
- Access the shared httpx client and config via the FastMCP lifespan context — never use module-level globals for these.
- **Tool functions call `make_nc_request` directly, never other tool functions** (tool independence convention). This enables isolated testing with `respx`.
- Return typed Pydantic models (or `Dict[str, Any]` for simple results). Validate responses with `Model.model_validate()`.
- Tool functions handle only the success path. Errors are raised by `make_nc_request` as `DeckAPIError` subclasses.

## Error Handling

- `make_nc_request` raises `DeckHTTPError` for HTTP status errors and `DeckConnectionError` for network/timeout errors.
- Never return error dicts from `make_nc_request` or tool functions.
- FastMCP surfaces exceptions to the MCP client automatically.

## Pydantic Models

- All fields `Optional` with `None` default — Nextcloud API responses are sparse.
- Use `Union` types where the API returns inconsistent types (e.g., `owner` can be `str` or `Owner`).
- Models live in `models.py` with no business logic.

## HTTP Requests

- Use `make_nc_request(method, endpoint, **kwargs)` in `client.py` for all Nextcloud Deck API calls.
- Never construct URLs manually in tool functions.
- The httpx client is created once in the lifespan hook with a 30s default timeout.

## Config

- All configuration comes from environment variables, loaded and validated in `config.py` as a frozen `DeckConfig` dataclass.
- Required vars: `NC_URL`, `NC_USER`, `NC_APP_PASSWORD`.
- Optional vars: `NC_API_VERSION` (default `v1.1`), `MCP_TRANSPORT` (default `stdio`), `MCP_REQUEST_TIMEOUT` (default `30.0`).
- Validation happens at startup in the lifespan hook — fail fast if required vars are missing.

## Secrets & Security

- Credentials come from environment / `.env` only.
- Never log, print, or include credentials or full API response bodies in error messages.
- `.env` is gitignored — never commit it.

## Style

- Format with standard Python conventions (PEP 8).
- Use type hints on all function signatures.
- Do not shadow Python builtins (e.g., use `card_type` instead of `type`).
