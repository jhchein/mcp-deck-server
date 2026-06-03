# mcp-deck-server

A local MCP server for Nextcloud Deck. It lets an agent list boards, inspect stacks, create and update cards, move cards between stacks, and manage labels or assignees through the Deck API.

The server is intentionally local: it runs over stdio and does not expose an HTTP listener.

## What you need

You need Python, uv, and a Nextcloud account that can access the Deck boards the agent should manage. Use a dedicated low-privilege Nextcloud user when you can. Nextcloud app passwords are account credentials, not Deck-only tokens.

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Nextcloud with the [Deck app](https://apps.nextcloud.com/apps/deck)
- A Nextcloud app password from Settings > Security > Devices & sessions

## Quick start

Install dependencies, create a `.env`, then run the server.

```bash
uv sync
```

```env
NC_URL=https://your-nextcloud-instance.example.com
NC_USER=your-agents-username
NC_APP_PASSWORD=your-app-password
```

```bash
uv run main.py
```

Configuration is validated at startup. Missing required values, invalid URLs, and invalid timeout values fail before the MCP server starts.

## Configuration

The `.env` file lives in the project root. Keep it out of source control.

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `NC_URL` | Yes | None | Absolute `http` or `https` Nextcloud base URL. No query string or fragment. |
| `NC_USER` | Yes | None | Nextcloud user ID for the MCP server. |
| `NC_APP_PASSWORD` | Yes | None | Device-specific app password for `NC_USER`. |
| `NC_API_VERSION` | No | `v1.1` | Deck API version. |
| `MCP_REQUEST_TIMEOUT` | No | `30.0` | HTTP request timeout in seconds. |

For live integration and performance checks, add this only when you have a board that can safely receive disposable test cards:

```env
DECK_TEST_BOARD_ID=6
```

## MCP client config

Point your MCP client at `uv run main.py` from this repository. Example shape:

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

Use the Windows path style in `cwd` when configuring a Windows client.

## Tools

The tool names are small on purpose. IDs come from Deck, so start with `list_boards` and `list_stacks` when you are exploring a board for the first time.

| Tool | Parameters | Returns |
| --- | --- | --- |
| `list_boards` | None | `list[Board]` |
| `get_board` | `board_id` | `Board` |
| `list_stacks` | `board_id` | `list[Stack]` |
| `list_cards` | `board_id`, `stack_id`, `done?` | `list[Card]` |
| `get_assigned_cards` | `user_id?`, `board_ids?`, `done?` | `list[CardResult]` |
| `create_card` | `board_id`, `stack_id`, `title`, `description?` | `Card` |
| `get_card` | `board_id`, `stack_id`, `card_id` | `Card` |
| `update_card` | `board_id`, `stack_id`, `card_id`, optional card fields | `Card` |
| `move_card` | `board_id`, `card_id`, `target_stack_name` | `Card` |
| `archive_card` | `board_id`, `stack_id`, `card_id` | `Card` |
| `assign_label_to_card` | `board_id`, `stack_id`, `card_id`, `label_id` | `dict` |
| `remove_label_from_card` | `board_id`, `stack_id`, `card_id`, `label_id` | `dict` |
| `assign_user_to_card` | `board_id`, `stack_id`, `card_id`, `user_id` | `dict` |
| `unassign_user_from_card` | `board_id`, `stack_id`, `card_id`, `user_id` | `dict` |

Two tools have behavior worth calling out.

`update_card` fetches the current card, merges the fields you provide, and sends the full Deck payload back. For text and datetime fields, `None` means keep the current value. For nullable text and datetime fields, `""` means clear the value. `done` is an ISO-8601 datetime string or `""`, never a boolean.

`move_card` resolves `target_stack_name` case-insensitively, uses the target-stack reorder endpoint, and verifies the card actually ended up in the target stack. If the stack name is wrong, the error includes the available stack names.

## Project layout

The implementation is deliberately flat. `server.py` owns the MCP tools, `client.py` owns HTTP behavior, `models.py` owns response shapes, and `config.py` owns environment parsing.

```text
main.py
mcp_deck_server/
    __init__.py
    client.py
    config.py
    models.py
    server.py
tests/
    fixtures/
    integration/
    unit/
project-spec/
    decisions/
docs/
    performance.md
    security.md
```

Dependency direction stays simple:

```text
config.py <- client.py <- server.py <- main.py
models.py <- server.py
```

## Development

Use uv for local work.

```bash
uv sync --dev
```

Run the normal checks before opening a PR:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/unit tests/test_timing.py -m "not integration"
uv audit
```

Live tests need a configured `.env`. The mutation performance test also needs `DECK_TEST_BOARD_ID`, because it creates, moves, and archives a disposable card.

```bash
uv run pytest tests/integration -m integration
uv run pytest tests/integration/test_live_performance.py -s -m "integration and slow"
```

## CI and branch protection

CI runs lint, unit tests with coverage, audit, and optional live jobs. `integration` and `benchmarks` are intentionally not required on PRs because they need secrets or a live Nextcloud instance.

Required checks for `main` should be:

- `lint`
- `test`
- `audit`

Keep `integration` and `benchmarks` informational.

## Current reviews

The current security and performance positions are documented separately:

- [docs/security.md](docs/security.md)
- [docs/performance.md](docs/performance.md)

Short version: the local stdio deployment is acceptable for a trusted local MCP client, and current performance is fast enough for normal single-user MCP use. The broad unscoped assigned-card scan is the path to watch if the account gains access to many boards.
