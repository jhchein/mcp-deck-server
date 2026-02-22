# Interfaces

Contracts only — signatures, schemas, auth claims. Not implementation.

## MCP Tools

All tools are async, registered via `@mcp.tool()` on the `FastMCP("deck")` instance in `server.py`.
Tools access the shared httpx client and config via the FastMCP lifespan context.
Tools call `make_nc_request` directly — never other tool functions (tool independence convention).

| Tool                     | Parameters                                                                                       | Returns       |
| ------------------------ | ------------------------------------------------------------------------------------------------ | ------------- |
| `list_boards`            | —                                                                                                | `List[Board]` |
| `get_board`              | `board_id: int`                                                                                  | `Board`       |
| `list_stacks`            | `board_id: int`                                                                                  | `List[Stack]` |
| `list_cards`             | `board_id: int, stack_id: int`                                                                   | `List[Card]`  |
| `create_card`            | `board_id: int, stack_id: int, title: str, description: str = ""`                                | `Card`        |
| `get_card`               | `board_id: int, stack_id: int, card_id: int`                                                     | `Card`        |
| `update_card`            | `board_id: int, stack_id: int, card_id: int, title?, description?, duedate?, card_type?, owner?` | `Card`        |
| `move_card`              | `board_id: int, card_id: int, target_stack_name: str`                                            | `Card`        |
| `archive_card`           | `board_id: int, stack_id: int, card_id: int`                                                     | `Card`        |
| `assign_label_to_card`   | `board_id: int, stack_id: int, card_id: int, label_id: int`                                      | `Dict`        |
| `remove_label_from_card` | `board_id: int, stack_id: int, card_id: int, label_id: int`                                      | `Dict`        |

## Nextcloud Deck API

- Base URL: `{NC_URL}/index.php/apps/deck/api/v1.1`
- Auth: HTTP Basic (`NC_USER` / `NC_APP_PASSWORD`)
- Headers: `OCS-APIRequest: true`, `Content-Type: application/json`

## Exception Hierarchy

All exceptions live in `client.py`.

```
DeckAPIError(Exception)           # Base — all Deck API errors
├── DeckHTTPError(DeckAPIError)   # HTTP status errors (has .status_code, .body)
└── DeckConnectionError(DeckAPIError)  # Network / timeout errors
```

## Config Contract

`config.py` exports a frozen dataclass:

```python
@dataclasses.dataclass(frozen=True)
class DeckConfig:
    nc_url: str           # Required. No trailing slash.
    nc_user: str          # Required.
    nc_app_password: str  # Required.
    nc_api_version: str   # Default "v1.1"
    transport: str        # "stdio" | "sse". Default "stdio".
    request_timeout: float  # Default 30.0 seconds.
```

Loaded from environment variables: `NC_URL`, `NC_USER`, `NC_APP_PASSWORD`, `NC_API_VERSION`, `MCP_TRANSPORT`, `MCP_REQUEST_TIMEOUT`.
Validated at startup in the lifespan hook — raises `ValueError` immediately if required vars are missing.

## Module Dependency Graph

All modules live in `mcp_deck_server/` (flat at repo root, not `src/` layout).

```
config.py  ←──  client.py  ←──  server.py  ←──  main.py
models.py  ←──  client.py
models.py  ←──  server.py
```

`config.py` and `models.py` are leaf modules with zero intra-project imports.
