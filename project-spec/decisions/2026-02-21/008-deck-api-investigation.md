# Decision: Nextcloud Deck API investigation and model validation

**Date:** 2026-02-21
**Status:** Accepted

## Context

The current Pydantic models were built empirically from observed API responses. We need a thorough investigation of the Nextcloud Deck REST API to ensure:

1. Our models cover the full response surface (no missing fields that cause silent data loss).
2. We handle all error codes the API can return.
3. We're not missing useful endpoints that could improve tool functionality.
4. We understand rate limiting, pagination, and ETags behavior.

## Decision

### Investigation scope

Conduct a thorough review of the Nextcloud Deck API using:

- Official Deck API documentation: `https://deck.readthedocs.io/en/latest/API/`
- Nextcloud Deck GitHub repo API routes: `https://github.com/nextcloud/deck`
- Actual API responses captured against a running instance (stored in `tests/fixtures/`).

### Areas to investigate

| Area                  | Questions to answer                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Endpoints**         | Are we missing any useful endpoints? (comments, attachments, activity, undo-delete, board sharing, user assignment to cards)   |
| **Response shapes**   | Do our Pydantic models match the full documented schema? Are there fields we're ignoring?                                      |
| **Error responses**   | What HTTP status codes does Deck return? (400, 403, 404, 409, 412, 429?) What's the error body shape?                          |
| **Pagination**        | Does any endpoint paginate? If so, how? (Link headers, offset params?)                                                         |
| **ETags**             | Deck uses `If-None-Match` / ETags for caching — should we leverage this?                                                       |
| **Rate limiting**     | Does Nextcloud or Deck enforce rate limits? How are they signaled?                                                             |
| **Permissions model** | What permissions exist (PERMISSION_READ, PERMISSION_EDIT, PERMISSION_MANAGE, PERMISSION_SHARE)? How do they map to API errors? |
| **Board types**       | Does the API differentiate personal vs shared boards?                                                                          |
| **Card assignments**  | Current models show `assignedUsers` — is there a dedicated assign/unassign endpoint?                                           |

### Deliverables

1. **API reference doc** in `docs/deck-api-reference.md` — summarizes all endpoints, request/response shapes, error codes, and pagination behavior relevant to this server.
2. **Model validation report** — diff between current Pydantic models and the full documented API schema, with recommendations for additions or corrections.
3. **Updated `tests/fixtures/`** — real API response snapshots for every endpoint we use, plus edge cases (empty board, large board, error responses).
4. **Recommendations** — new tools to add, endpoints to support, model changes needed.

## Consequences

- Ensures models are complete and robust, not just "works for the cases I tested."
- Fixture snapshots become the source of truth for unit tests.
- May reveal additional tools worth exposing (comments, attachments, user assignment).
- Investigation findings get documented in `docs/` for ongoing reference.
