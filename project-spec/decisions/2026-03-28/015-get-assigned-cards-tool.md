# Decision 015 — `get_assigned_cards` Tool & `Assignment` Model Fix

**Date:** 2026-03-28
**Status:** Accepted

## Context

The current MCP tool surface is entity-oriented: `list_boards`, `list_stacks`, `list_cards(board_id, stack_id)`. Answering "what cards are assigned to me?" requires the agent to orchestrate a multi-step fan-out (list boards → list stacks per board → filter cards by assigned user), which is fragile, token-expensive, and shifts domain knowledge onto the LLM consumer.

Additionally, the `Card.assignedUsers` model is incorrect. The Deck API returns assignment wrapper objects (`{ id, participant: Owner, cardId, type }`), but the model declares `list[Owner]`. Because `extra="allow"` silently absorbs unrecognized fields, the `uid` on parsed `Owner` objects is always `None`, making any user-based filtering silently broken.

## Decisions

### 1. New model: `Assignment`

Introduce an `Assignment` model that matches the actual API response shape for assigned users.

```python
class Assignment(DeckBaseModel):
    id: int | None = None
    participant: Owner | None = None
    cardId: int | None = None
    type: int | str | None = None
```

Change `Card.assignedUsers` from `list[Owner] | None` to `list[Assignment] | None`.

**Rationale:** The current type silently loses the `participant.uid` needed for filtering. This is a correctness fix, not a new feature. Must be validated against the live API before merging (following the decision 014 pattern).

### 2. New tool: `get_assigned_cards`

```python
@mcp.tool()
async def get_assigned_cards(
    user_id: str | None = None,
    board_ids: list[int] | None = None,
    done: bool | None = None,
) -> list[CardResult]:
```

**Parameters:**

| Parameter   | Type                | Default       | Behavior                                                                                                |
| ----------- | ------------------- | ------------- | ------------------------------------------------------------------------------------------------------- |
| `user_id`   | `str \| None`       | `None` → self | `None` uses `NC_USER` from config. Explicit value queries that user.                                    |
| `board_ids` | `list[int] \| None` | `None` → all  | `None` fetches all boards the authenticated user can access. Explicit list scopes to those boards only. |
| `done`      | `bool \| None`      | `None` → both | `None` returns all cards. `True` = only done. `False` = only not-done.                                  |

**Algorithm (conceptual):**

1. Resolve `user_id` → `NC_USER` if `None`
2. Resolve boards → `GET /boards` if `board_ids` is `None`; otherwise use provided IDs
3. For each board: `GET /boards/{id}/stacks` → extract all cards from all stacks
4. Filter: `card.assignedUsers` contains an entry where `assignment.participant.uid == user_id`
5. Filter: if `done` is not `None`, match `card.done` against requested value
6. Return enriched results with board/stack context

**Access control:** `GET /boards` only returns boards the authenticated user has `PERMISSION_READ` on. No additional scoping logic needed — the API is the access boundary. If `board_ids` contains an inaccessible board, the stacks request returns 403, surfaced as `DeckHTTPError`.

### 3. Return shape: `CardResult`

Each result includes board/stack context so the consumer knows where each card lives:

```python
class CardResult(DeckBaseModel):
    board_id: int
    board_title: str
    stack_id: int
    stack_title: str
    card: Card
```

The tool returns `list[CardResult]`. This is a read-only view model — not used for write operations.

**Why not flat `list[Card]`?** Cards carry `stackId` but not `boardId` or human-readable names. The agent needs context to communicate results meaningfully ("your card X is in column Y on board Z").

### 4. Tool name: `get_assigned_cards`

Rejected alternatives:

| Name            | Rejection reason                               |
| --------------- | ---------------------------------------------- |
| `search_cards`  | Implies text/content search, which this is not |
| `list_my_cards` | Awkward when `user_id` override is used        |
| `filter_cards`  | Too generic / technical                        |
| `query_cards`   | Also implies search                            |

`get_assigned_cards` is self-documenting: it gets cards by assignment. The `user_id` default-to-self makes the zero-arg "get my cards" the natural first call.

### 5. `done` field semantics

**Superseded by decision 016:** `Card.done` is an ISO-8601 datetime string (`str | None`), not a boolean. The `done` filter in `get_assigned_cards` is a `bool` predicate: `done=True` matches cards where `card.done is not None`, `done=False` matches `card.done is None`.

## Performance Characteristics

- **O(boards)** API calls: 1 `GET /boards` + N `GET /stacks` where N = number of boards queried
- For <10 boards on a private instance, this is bounded at <11 HTTP calls, well under the 30s timeout
- No parallel fan-out in v1 — sequential is simpler and sufficient at this scale
- Future optimization: `asyncio.gather` for parallel stacks fetches if N grows

## Consequences

- `models.py`: Add `Assignment` class; change `Card.assignedUsers` type
- `server.py`: Add `get_assigned_cards` tool function, add `CardResult` model (or in `models.py`)
- `tests/fixtures/`: Add fixture with populated `assignedUsers` for model/tool coverage; live capture remains pending
- `tests/unit/test_models.py`: Add `Assignment` parsing tests
- `tests/unit/test_tools.py`: Add `get_assigned_cards` tests (user filter, board filter, done filter, empty results)
- `interfaces.md`: Add tool to table; document `Assignment` and `CardResult` models
- **Follow-up:** Validate `assignedUsers` wrapper shape against live API in this repo's integration environment

## Reversibility

Two-way door. The new tool is read-only, additive, and independent of existing tools. The model fix is also additive (`extra="allow"` means existing parsed data still works). Both can be removed without impact.
