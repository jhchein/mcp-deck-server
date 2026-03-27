# Decision 013 — Deck API Investigation Findings

**Date:** 2026-02-23
**Status:** Accepted
**Resolves:** Open questions from decisions 003, 008, 012

## Context

Phase 2a requires authoritative answers to key API behavior questions before we can finalize model validation, close conditional tasks, and scope future tools. Investigation was conducted against the official Deck API documentation at `https://deck.readthedocs.io/en/latest/API/`.

## Findings

### Q1: Do stacks embed cards?

**Yes.** `GET /boards/{boardId}/stacks` returns `"cards": [...]` in each stack object.

**Impact:** Our `move_card` approach (1 GET stacks + 1 PUT reorder) is correct. No N+1 fallback needed. Conditional task closed.

### Q2: Does PUT card require a full payload?

**Yes — full replacement.** The PUT card docs list all fields (title, description, type, order, duedate) without "optional" markers. The example body includes every field.

**Impact:** Our fetch-merge pattern in `update_card` is correct and necessary. The `None`=keep / `""`=clear convention remains the right approach.

### Q3: Is there an official way to archive a card?

**No documented endpoint.** The official API documents `archived: bool` only in the PUT _board_ body. There is no archive field in the PUT card body, and no `/cards/{cardId}/archive` endpoint in the docs.

Our `PUT .../cards/{cardId}/archive` endpoint works empirically against live instances but is **undocumented**.

**Decision:** Pragmatic — keep the endpoint. Note it as undocumented in the tool reference. No official alternative exists.

### Q4: Pagination

Only the **Comments** OCS endpoint paginates (`limit`/`offset`, default 20). No board/stack/card REST endpoints paginate.

**Impact:** No pagination concern for current tools.

### Q5: ETags

Supported on GET boards, board detail, stacks, stack detail, card detail, attachments. `If-None-Match` header returns 304 when unchanged.

**Impact:** Future optimization opportunity (Phase 5 caching evaluation). No action now.

### Q6: Rate limiting

**Not documented** in Deck API docs. May exist at the Nextcloud platform level.

**Impact:** No action needed. `DeckHTTPError` already handles arbitrary status codes including 429.

### Q7: Error codes

Documented: 400 (bad request, with `{"status": 400, "message": "..."}` body), 403 (permission denied). 404 documented for comments only. No 429 documented.

**Impact:** Our `DeckHTTPError` already covers all cases. Error fixture coverage is adequate.

### Q8: `owner` field in PUT card

**Not documented.** The PUT card request data lists only: title, description, type, order, duedate. Our code sends `owner` in the payload — this is undocumented behavior.

**Decision:** Keep sending `owner` (server likely ignores unknown fields or honors it). Note as undocumented. Low risk.

## Model Observations

| Field                | API docs                      | Our model                 | Action                                          |
| -------------------- | ----------------------------- | ------------------------- | ----------------------------------------------- |
| `Owner.displayname`  | `displayname` (all lowercase) | `displayName` (camelCase) | Rename to `displayname` to match API            |
| `Card.commentsCount` | Not in create response        | Optional, defaults None   | No change needed                                |
| `Board.settings`     | `dict[str, Any]` only         | `list \| dict \| None`    | Remove `list` variant — API always returns dict |

## Endpoints Not Exposed (scoped)

| Endpoint                                      | Base URL                    | Disposition                                            |
| --------------------------------------------- | --------------------------- | ------------------------------------------------------ |
| Comments (CRUD)                               | OCS API (`/ocs/v2.php/...`) | Non-goal — different base URL, pagination, OCS wrapper |
| User assignment (`assignUser`/`unassignUser`) | REST API                    | **Promoted to Phase 2** — useful for agents            |
| Attachments (CRUD)                            | REST API                    | Non-goal — multipart file upload                       |
| Board/Stack/Label CRUD                        | REST API                    | Non-goal — managed via Nextcloud UI                    |
| ACL management                                | REST API                    | Non-goal — admin task                                  |
| Sessions                                      | OCS API                     | Non-goal — real-time UI sync                           |
| Board import                                  | REST API (v1.2 unreleased)  | Non-goal — niche                                       |

## Consequences

- Conditional tasks from decision 012 are resolved: stacks embed cards ✓, full PUT confirmed ✓
- `archive_card` kept as-is (pragmatic, no official alternative)
- `assignUser`/`unassignUser` tools promoted from P2-later to Phase 2 remaining
- Model corrections identified (displayname rename, settings type narrowing)
- No pagination or rate-limiting concerns for current scope
