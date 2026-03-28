# Decision 016 — `update_card` Exhaustive Fetch-Merge & `done` Field Semantics

**Date:** 2026-03-28
**Status:** Accepted
**Resolves:** `update_card` silently resets `description`, `duedate`, `order`, and (potentially) `done` when those parameters are not provided by the caller.

## Context

Investigation against the live Nextcloud Deck instance (`cloud.heinsight.de`, card 622) revealed two classes of bugs in `update_card`:

1. **Incomplete fetch-merge.** The current code builds the PUT payload with only `title`, `type`, and conditionally `description`, `duedate`, `owner`. Since PUT card is a full replacement (decision 013), every field omitted from the payload is reset to its server-side default.

2. **`done` field type mismatch.** The `Card.done` model field was typed `str | bool | None`. Live testing proves `done` is a datetime string (ISO-8601), not a boolean.

## Live API Findings

### Required PUT fields

| Payload                | Result                        |
| ---------------------- | ----------------------------- |
| `{title}`              | 400: "type must be provided"  |
| `{title, type}`        | 400: "owner must be provided" |
| `{title, type, owner}` | 200 OK — **minimum viable**   |

**`owner` is required** by the server despite being undocumented in the API docs. Confirmed — consistent with decision 013.

### Field reset on omission

After populating a card with `description="test"`, `duedate="2026-12-31..."`, `order=42`:

| Omitted field | Behavior                             |
| ------------- | ------------------------------------ |
| `description` | **RESET** to `""`                    |
| `duedate`     | **RESET** to `null`                  |
| `order`       | **RESET** to `0`                     |
| `done`        | Not independently tested (see below) |

### `done` field behavior

| Value sent                    | Result                                                      |
| ----------------------------- | ----------------------------------------------------------- |
| `"2026-03-28T12:00:00+00:00"` | 200 OK — `done` set to provided datetime                    |
| `null`                        | 200 OK — `done` cleared to `null`                           |
| omitted                       | 200 OK — `done` not independently tested for preservation   |
| `False`                       | 200 OK — server sets `done` to current server timestamp (!) |
| `""`                          | 200 OK — server preserves/sets `done` (ambiguous)           |
| `True`                        | **500 Internal Server Error**                               |
| `1`                           | **500 Internal Server Error**                               |
| `0`                           | **500 Internal Server Error**                               |
| `"true"`                      | **500 Internal Server Error**                               |

**Conclusion:** `done` is an ISO-8601 datetime string, semantic twin of `duedate`. `null` = not done, datetime = done at that time. Sending booleans or integers crashes the server (500). `False` has quirky behavior (server interprets it as "mark done now"), reinforcing that it must never be sent.

### Current `update_card` behavior (no-overrides path)

Sends `{title, type, owner}` only. **Result:** `description`, `duedate`, and `order` are all silently reset.

## Decisions

### 1. Model type change: `Card.done`

Change from `str | bool | None` to `str | None`.

- `None` = not done
- `str` = ISO-8601 datetime when the card was marked done

Add a comment: `# ISO-8601 datetime or null; same semantics as duedate`.

**Rationale:** `bool` is wrong — the API never returns a boolean for `done`, and sending boolean values either crashes the server (True, 500) or triggers surprising behavior (False → sets to current timestamp). Removing `bool` prevents downstream code from accidentally constructing invalid payloads.

### 2. Exhaustive fetch-merge in `update_card`

The PUT payload must always include **every** field the API accepts, using the fetched card's current values as defaults. The new payload construction:

```python
payload = {
    "title":       title       if title is not None       else current_card.title,
    "type":        card_type   if card_type is not None   else current_card.type or "plain",
    "order":       order       if order is not None       else current_card.order,
    "description": description if description is not None else current_card.description,
    "duedate":     current_card.duedate if duedate is None else (None if duedate == "" else duedate),
    "done":        current_card.done    if done is None    else (None if done == "" else done),
    "owner":       <existing owner merge logic>,
}
```

All fields are always present in the payload. Omission is no longer possible.

### 3. `duedate` and `done` keep / clear / set semantics

`duedate` and `done` use the same public tool convention as other text-like fields:

| Caller sends                  | Payload value                  |
| ----------------------------- | ------------------------------ |
| `None`                        | current card value (preserve)  |
| `""`                          | `None` in JSON payload (clear) |
| `"2026-12-31T00:00:00+00:00"` | the provided datetime string   |

The implementation translates empty string to JSON `null` before sending the PUT request. This preserves the existing caller experience (`None`=keep, `""`=clear) while still satisfying the Deck API's datetime-or-null contract.

### 4. New `update_card` signature

```python
@mcp.tool()
async def update_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    title: str | None = None,          # None = keep current
    description: str | None = None,     # None = keep, "" = clear
    duedate: str | None = None,         # None = keep, "" = clear, str = set ISO-8601
    done: str | None = None,            # None = keep, "" = clear, str = set ISO-8601
    card_type: str | None = None,       # None = keep current (was hardcoded "plain")
    owner: dict | None = None,          # None = keep current
    order: int | None = None,           # None = keep current
) -> Card:
```

**Breaking changes from current signature:**

| Parameter   | Before                        | After                                         | Reason                                                    |
| ----------- | ----------------------------- | --------------------------------------------- | --------------------------------------------------------- |
| `card_type` | `str = "plain"` (always sent) | `str \| None = None` (keep unless overridden) | Can't distinguish "caller wants plain" from "didn't pass" |
| `duedate`   | `str \| None = None`          | `str \| None = None`                          | `None` keeps current, `""` clears, datetime string sets   |
| `done`      | not exposed                   | `str \| None = None`                          | New parameter — datetime, not boolean                     |
| `order`     | not exposed                   | `int \| None = None`                          | New parameter — was silently reset to 0                   |

### 5. `get_assigned_cards` `done` filter update

The `done` parameter in `get_assigned_cards` (decision 015) stays as `bool | None` — it's a **filter predicate** ("show done cards? yes/no/both"), not a value to write. The internal filter uses truthiness: `done is not None` → truthy match. No change needed to the filter signature, but the `_card_matches_done_filter` docstring should note that `card.done` is a datetime string, not a boolean.

### 6. Test fixture update

The `card.json` fixture has `"done": null`. This remains valid — `null` is the common case. Add a second fixture variant `card_done.json` with `"done": "2026-03-28T12:00:00+00:00"` for testing the done-set state.

## Consequences

- `Card.done` type narrows from `str | bool | None` to `str | None`
- `update_card` sends all 7 fields in every PUT (title, type, order, description, duedate, done, owner)
- No optional field can be silently reset — the fetch-merge is exhaustive
- `card_type` default changes from `"plain"` to `None` — existing callers that relied on the implicit `"plain"` default will now preserve the card's existing type instead
- `done` and `order` become user-controllable through `update_card`
- Existing unit tests must be updated to match new payload assertions (all fields always present)
