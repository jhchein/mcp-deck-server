# Decision 014 — Live API Validation Findings

**Date:** 2026-03-27
**Status:** Accepted
**Resolves:** Phase 2 remaining: "Validate Pydantic models against actual API responses"

## Context

Live integration testing against a real Nextcloud Deck instance (`cloud.heinsight.de`) revealed two contract mismatches between our models/tools and the actual API behavior.

## Finding 1: `Board.settings` is `[]` on `GET /boards`, `{}` on `GET /boards/{id}`

**Root cause:** The upstream `BoardService.enrichBoards()` only calls `enrichWithBoardSettings()` when the `$fullDetails` parameter is `true`. The `GET /boards` API controller passes `$details` (from `?details=` query param, default `false`), so settings are NOT populated and the PHP default `protected $settings = []` is serialized as JSON `[]`.

| Endpoint                   | `fullDetails`   | `settings` shape                         |
| -------------------------- | --------------- | ---------------------------------------- |
| `GET /boards` (default)    | `false`         | `[]` (empty PHP array → JSON `[]`)       |
| `GET /boards?details=true` | `true`          | `{"notify-due": "...", "calendar": ...}` |
| `GET /boards/{boardId}`    | `true` (always) | `{"notify-due": "...", "calendar": ...}` |

**Not a version issue.** This is intentional upstream behavior — the board list endpoint returns a lightweight representation.

**Decision:** Widen `Board.settings` to `list[Any] | dict[str, Any] | None` to accept both shapes. This is the correct defensive posture for a client library consuming an API where the same field varies by endpoint.

**Correction to decision 013:** The recommendation to "remove list variant — API always returns dict" was based on docs-only investigation. Live validation proves the list variant is real and must be supported.

## Finding 2: `GET /boards/{boardId}/stacks/{stackId}/cards` returns 405

**Root cause:** This endpoint does not exist in the upstream route definitions. The registered API routes for cards are:

- `card_api#get` → `GET /api/v{apiVersion}/boards/{boardId}/stacks/{stackId}/cards/{cardId}` (single card)
- `card_api#create` → `POST /api/v{apiVersion}/boards/{boardId}/stacks/{stackId}/cards` (create)

There is no `card_api#index` route for listing cards by stack. The URL `/cards` only has a POST handler, so GET returns 405 Method Not Allowed.

Cards are available through:

1. **Embedded in stacks** — `GET /boards/{boardId}/stacks` returns cards in each stack object
2. **Individual fetch** — `GET /boards/{boardId}/stacks/{stackId}/cards/{cardId}`

**Decision:** Rewrite `list_cards` to extract cards from the stacks response instead of calling a non-existent endpoint. This follows the same pattern `move_card` already uses.

## Finding 3: `Card.lastEditor` can be a string

Live `archive_card` response returned `"lastEditor": "nc_agent"` (a plain string), but the model expected `Owner | None`. This follows the same pattern as `Card.owner` (can be object or string).

**Decision:** Widen `Card.lastEditor` to `Owner | str | None`.

## Finding 4: `move_card` reorder returns the first card from the affected list

The `PUT .../cards/{cardId}/reorder` endpoint returns a list of all affected cards in the target stack. Our `move_card` implementation takes `response[0]`, which may not be the card that was moved. This is a pre-existing known behavior, not a regression.

## Consequences

- `Board.settings` type widened: `list[Any] | dict[str, Any] | None`
- `Card.lastEditor` type widened: `Owner | str | None`
- Unit test `test_board_settings_list_is_rejected` replaced with `test_board_settings_list_is_accepted`
- `list_cards` tool rewritten to use stacks endpoint
- `list_cards` unit tests updated accordingly
- Live contract integration test covers all 13 tool endpoints in one round-trip
- Decision 013 model observations table corrected
