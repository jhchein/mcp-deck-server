# Decision: Use stacks response for card lookup in `move_card`

**Date:** 2026-02-21
**Status:** Accepted

## Context

`move_card` currently calls `list_stacks(board_id)` and then calls `list_cards(board_id, stack.id)` for each stack to find the card's current location. This is an N+1 query pattern — on a board with many stacks, it causes multiple sequential API calls.

The Nextcloud Deck `GET /boards/{id}/stacks` endpoint already returns cards nested inside each stack's response payload.

## Decision

1. Use the `stacks[].cards[]` data from the `list_stacks` response directly.
2. Do not issue separate `list_cards` calls per stack.
3. This reduces `move_card` to 2 API calls total: one GET (list stacks with cards) + one PUT (reorder).

## Consequences

- Significantly faster `move_card` on boards with multiple stacks.
- Simpler code — no try/except loop over stacks.
- Relies on `list_stacks` returning cards in the response, which is the default Nextcloud Deck API behavior.
