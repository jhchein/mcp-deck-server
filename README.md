# mcp-deck-server

MCP tool server that lets AI agents manage Nextcloud Deck kanban boards.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A Nextcloud instance with the [Deck app](https://apps.nextcloud.com/apps/deck) installed
- A Nextcloud app password (Settings → Security → Devices & sessions)

## Configuration

Create a `.env` file in the project root:

```env
NC_URL=https://your-nextcloud-instance.example.com
NC_USER=your-agents-username
NC_APP_PASSWORD=your-app-password
```

| Variable              | Required | Default | Description                            |
| --------------------- | -------- | ------- | -------------------------------------- |
| `NC_URL`              | Yes      | —       | Nextcloud base URL (no trailing slash) |
| `NC_USER`             | Yes      | —       | Nextcloud username                     |
| `NC_APP_PASSWORD`     | Yes      | —       | Nextcloud app password                 |
| `NC_API_VERSION`      | No       | `v1.1`  | Deck API version                       |
| `MCP_REQUEST_TIMEOUT` | No       | `30.0`  | HTTP request timeout in seconds        |

Configuration is validated at startup. Missing required variables cause an immediate `ValueError`.

## Running

```bash
uv run main.py
```

The server uses stdio transport exclusively, intended for local MCP clients (Claude Desktop, VS Code, etc.).

### MCP Client Configuration

Add to your MCP client config (e.g., Claude Desktop `claude_desktop_config.json` or VS Code `settings.json`):

```json
{
  "mcpServers": {
    "deck": {
      "command": "uv",
      "args": ["run", "main.py"],
      "cwd": "/path/to/mcp-deck-server"
    }
  }
}
```

## Tools

| Tool                      | Parameters                                                                                       | Returns            |
| ------------------------- | ------------------------------------------------------------------------------------------------ | ------------------ |
| `list_boards`             | —                                                                                                | `List[Board]`      |
| `get_board`               | `board_id`                                                                                       | `Board`            |
| `list_stacks`             | `board_id`                                                                                       | `List[Stack]`      |
| `list_cards`              | `board_id, stack_id`                                                                             | `List[Card]`       |
| `get_assigned_cards`      | `user_id?, board_ids?, done?`                                                                    | `List[CardResult]` |
| `create_card`             | `board_id, stack_id, title, description?`                                                        | `Card`             |
| `get_card`                | `board_id, stack_id, card_id`                                                                    | `Card`             |
| `update_card`             | `board_id, stack_id, card_id, title?, description?, duedate?, done?, card_type?, owner?, order?` | `Card`             |
| `move_card`               | `board_id, card_id, target_stack_name`                                                           | `Card`             |
| `archive_card`            | `board_id, stack_id, card_id`                                                                    | `Card`             |
| `assign_label_to_card`    | `board_id, stack_id, card_id, label_id`                                                          | `Dict`             |
| `remove_label_from_card`  | `board_id, stack_id, card_id, label_id`                                                          | `Dict`             |
| `assign_user_to_card`     | `board_id, stack_id, card_id, user_id`                                                           | `Dict`             |
| `unassign_user_from_card` | `board_id, stack_id, card_id, user_id`                                                           | `Dict`             |

`update_card` uses a fetch-merge pattern: it GETs the current card, merges provided fields, and PUTs the full payload. `None` = keep current value, `""` = clear. The `done` field accepts an ISO-8601 datetime string or `""` to clear — never a boolean.

`move_card` resolves `target_stack_name` case-insensitively. On mismatch, the error includes available stack names.

## Project Structure

```
main.py                     # Entrypoint: imports and runs the FastMCP server (stdio)
mcp_deck_server/
    __init__.py              # Re-exports mcp instance
    config.py                # DeckConfig dataclass + env-var loader
    models.py                # Pydantic models (Board, Stack, Card, Owner, Label, etc.)
    client.py                # make_nc_request + exception hierarchy
    server.py                # FastMCP instance, lifespan hook, tool registrations
tests/
    unit/                    # Unit tests (respx-mocked)
    integration/             # Live Nextcloud integration tests (secrets-gated)
    fixtures/                # Captured API response fixtures
project-spec/               # Canonical spec: constraints, interfaces, decisions
```

Module dependency graph:

```
config.py  ←──  client.py  ←──  server.py  ←──  main.py
models.py  ←──  server.py
```

`config.py` and `models.py` are leaf modules with no intra-project imports.

## Development

Install dev dependencies:

```bash
uv sync --group dev
```

### Linting & Type Checking

```bash
uv run ruff check .
uv run pyright
```

### Tests

```bash
uv run pytest                          # unit tests
uv run pytest --cov --cov-report=term-missing  # with coverage
uv run pytest -m integration           # integration tests (requires live Nextcloud + env vars)
```

### CI

GitHub Actions workflow (`.github/workflows/ci.yml`) runs:

- **lint** — ruff + pyright
- **test** — pytest unit + coverage (80% gate)
- **integration** — optional, secrets-gated, on `main` or manual trigger
- **benchmarks** — informational, non-blocking, `main`/manual only
- **audit** — `uv audit`

### Branch Protection

Recommended settings for the `main` branch:

- Require a pull request before merging
- Require at least 1 approving review
- Dismiss stale approvals when new commits are pushed
- Require conversation resolution before merge (optional, but recommended)
- Require branches to be up to date before merging

Required status checks (must match job names in `.github/workflows/ci.yml`):

- `lint`
- `test`
- `audit`

Checks that should **not** be required:

- `integration` (main/manual + secrets-gated)
- `benchmarks` (informational, non-blocking)

## Security

- Secrets (`NC_URL`, `NC_USER`, `NC_APP_PASSWORD`) are loaded from `.env` and never logged or embedded in responses.
- Board/card content may contain personal data — request/response payloads are not logged.
- The server runs locally over stdio; there is no network-facing attack surface.
