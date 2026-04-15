# Interfaces

Contracts only — signatures, schemas, auth claims. Not implementation.

## MCP Tools

All tools are async, registered via `@mcp.tool()` on the `FastMCP("deck")` instance in `server.py`.
Tools access the shared httpx client and config via the FastMCP lifespan context.
Tools call `make_nc_request` directly — never other tool functions (tool independence convention).
Tool docstrings and `Annotated[..., Field(description=...)]` parameter hints are part of the agent-facing MCP schema contract (decision 017).

| Tool                      | Parameters                                                                                                      | Returns            |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------ |
| `list_boards`             | —                                                                                                               | `List[Board]`      |
| `get_board`               | `board_id: int`                                                                                                 | `Board`            |
| `list_stacks`             | `board_id: int`                                                                                                 | `List[Stack]`      |
| `list_cards`              | `board_id: int, stack_id: int, done?: bool`                                                                     | `List[Card]`       | <!-- extracts from stacks endpoint; no dedicated cards-list API exists (decision 014); done filter matches get_assigned_cards semantics --> |
| `create_card`             | `board_id: int, stack_id: int, title: str, description: str = ""`                                               | `Card`             |
| `get_card`                | `board_id: int, stack_id: int, card_id: int`                                                                    | `Card`             |
| `update_card`             | `board_id: int, stack_id: int, card_id: int, title?, description?, duedate?, done?, card_type?, owner?, order?` | `Card`             | <!-- decision 016: exhaustive fetch-merge; done/order added; card_type default changed to None -->           |
| `move_card`               | `board_id: int, card_id: int, target_stack_name: str`                                                           | `Card`             |
| `archive_card`            | `board_id: int, stack_id: int, card_id: int`                                                                    | `Card`             |
| `assign_label_to_card`    | `board_id: int, stack_id: int, card_id: int, label_id: int`                                                     | `Dict`             |
| `remove_label_from_card`  | `board_id: int, stack_id: int, card_id: int, label_id: int`                                                     | `Dict`             |
| `assign_user_to_card`     | `board_id: int, stack_id: int, card_id: int, user_id: str`                                                      | `Dict`             |
| `unassign_user_from_card` | `board_id: int, stack_id: int, card_id: int, user_id: str`                                                      | `Dict`             |
| `get_assigned_cards`      | `user_id?: str, board_ids?: list[int], done?: bool`                                                             | `List[CardResult]` | <!-- decision 015; done is a filter predicate (truthy match on card.done datetime), not a value to write --> |

## Nextcloud Deck API

- Base URL: `{NC_URL}/index.php/apps/deck/api/v1.1`
- Auth: HTTP Basic (`NC_USER` / `NC_APP_PASSWORD`)
- Headers: `OCS-APIRequest: true`, `Content-Type: application/json`
- PUT card is **full replacement** — all fields required (decision 013)
- PUT card required fields (live-validated, decision 016): `title`, `type`, `owner`. Optional: `description`, `order`, `duedate`, `done`
- Omitting optional fields from PUT resets them to defaults (`""` / `null` / `0`) — full payload must always be sent
- `done` field is an ISO-8601 datetime string (like `duedate`), NOT a boolean. `null` = not done, datetime = done. Sending bool/int crashes the server (500)
- No pagination on board/stack/card endpoints (only OCS Comments)
- ETags supported on GET endpoints (`If-None-Match` → 304)
- `archive_card` endpoint is **undocumented** — works empirically, no official alternative (decision 013)
- `owner` field in PUT card payload is **undocumented but required** — server returns 400 without it (decisions 013, 016)

## Models — `Assignment`, `CardResult` (decision 015), `Card.done` narrowing (decision 016)

```python
class Assignment(DeckBaseModel):
    id: int | None = None
    participant: Owner | None = None
    cardId: int | None = None
    type: int | str | None = None

class CardResult(DeckBaseModel):
    board_id: int
    board_title: str
    stack_id: int
    stack_title: str
    card: Card
```

- `Card.assignedUsers` type changes from `list[Owner] | None` to `list[Assignment] | None`
- `Card.done` type changes from `str | bool | None` to `str | None` — it's an ISO-8601 datetime, not a boolean (decision 016)
- `Assignment` matches the actual Deck API response shape (`assignUser` endpoint returns `{ id, participant: Owner, cardId, type }`)
- `CardResult` is a read-only view model for `get_assigned_cards` — enriches cards with board/stack context

## Exception Hierarchy

All exceptions live in `client.py`.

```text
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
    request_timeout: float  # Default 30.0 seconds.
```

Loaded from environment variables: `NC_URL`, `NC_USER`, `NC_APP_PASSWORD`, `NC_API_VERSION`, `MCP_REQUEST_TIMEOUT`.
Validated at startup in the lifespan hook — raises `ValueError` immediately if required vars are missing.

## Module Dependency Graph

All modules live in `mcp_deck_server/` (flat at repo root, not `src/` layout).

```text
config.py  ←──  client.py  ←──  server.py  ←──  main.py
models.py  ←──  server.py
```

`config.py` and `models.py` are leaf modules with zero intra-project imports.
`client.py` imports `config.py` only and returns raw API payloads for validation in `server.py`.
