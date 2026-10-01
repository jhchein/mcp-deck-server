# Performance review

This review records the first measured performance baseline for the Deck MCP server. We measured repeatable mocked paths and one live Nextcloud Deck instance. The live environment is intentionally anonymized: no host name, user name, board ID, card titles, or credentials are recorded here.

## Summary

The current implementation is fast enough for normal MCP use. Every live tool path measured on the configured test board completed below one second, including disposable-card `move_card`. The broadest read path, unscoped `get_assigned_cards`, was the slowest because it scans every accessible board, but it still completed below the advisory threshold for an instant-feeling tool call in this baseline.

This review recommended no performance code changes at the time. Decision 018 later added concurrent board scanning and compact output (see below). The only other follow-up worth keeping is conditional caching research for `list_boards`, because that endpoint returned an ETag and honored `If-None-Match`. Stack payloads did not expose an ETag in this run, and both checked endpoints sent `Cache-Control: no-cache, no-store, must-revalidate`, so caching must stay conservative.

## Review thresholds

These thresholds are guidance for human review, not CI gates. Live Nextcloud latency depends on network, server load, board shape, and account access, so hard pass/fail limits would be noisy.

| Latency | Interpretation |
| --- | --- |
| `< 1s` | Feels instant enough for a normal MCP tool call. |
| `1-3s` | Acceptable, but worth noting when the path is common. |
| `3-10s` | Noticeable. Needs explanation, guidance, or a follow-up item. |
| `> 10s` | Needs remediation or a clear reason to accept the cost. |

## How to refresh the measurements

Use the mocked timing test for repeatable local checks. It does not require credentials and is the right place to confirm call counts, parsing cost, timeout behavior, and shared-client behavior.

```bash
uv run pytest tests/test_timing.py -s -m slow
```

Use the live performance test when `.env` contains `NC_URL`, `NC_USER`, and `NC_APP_PASSWORD`. Read-only measurements can fall back to the first accessible board. Live mutation measurements require an explicit test board selector.

```powershell
$env:DECK_TEST_BOARD_ID = "<test-board-id>"
uv run pytest tests/integration/test_live_performance.py -s -m "integration and slow"
```

## Mocked baseline

The mocked tests isolate our code from live network variance. They are useful for regression checks, not for claiming real user latency.

| Area | Measurement | Result |
| --- | --- | --- |
| Shared client reuse | 10 mocked `GET /boards` calls with one shared client | `6.74 ms` total |
| Per-request client creation | 10 mocked `GET /boards` calls with a new client each time | `281.93 ms` total |
| `move_card` normal path | Stack lookup plus target-stack reorder | `2` API calls, `1.61 ms` |
| Pydantic parsing | 5 stacks, 125 cards, 50,015 byte payload, 50 iterations | `44.60 ms` total, `0.89 ms` per iteration |
| Simulated timeout | `httpx.ReadTimeout` mapped to `DeckConnectionError` | `0.36 ms` |
| Concurrent calls | 5 `list_boards` plus 5 `list_stacks` calls | `6.35 ms` total |

The mocked numbers support the existing architecture. The shared client avoids repeated client setup cost, `move_card` stays on the expected two-call path, and Pydantic parsing is not a bottleneck at the tested payload size.

## Live baseline

This run used API version `v1.1`, six accessible boards, and a configured test board with four stacks and three cards. The test created one disposable card, moved it once, and archived it during cleanup.

| Tool path | Result |
| --- | --- |
| `list_boards` | `440.07 ms` |
| `get_board` | `85.31 ms` |
| `list_stacks` | `82.78 ms` |
| `list_cards` for the first stack | `93.01 ms` |
| `get_assigned_cards(board_ids=[...])` | `112.67 ms` |
| `get_assigned_cards()` across all accessible boards | `727.99 ms` |
| Concurrent `list_boards` and `list_stacks` | `323.99 ms` |
| Create disposable card | `162.41 ms` |
| Move disposable card | `267.35 ms` |
| Archive disposable card cleanup | `158.63 ms` |

The live numbers are comfortably below one second. The broad assigned-card scan is the path to watch because it scales with the number of accessible boards, but this baseline does not justify adding cache state or more complex request planning.

## Concurrent scan and compact output

Decision 018 changed `get_assigned_cards` to fetch boards concurrently, at most five at a time. We measured it live against the same anonymized instance (six accessible boards, 26 assigned cards) with three consecutive runs, and compared it with a sequential loop over the same requests.

| Measurement | Result |
| --- | --- |
| Sequential `GET /boards` plus one `GET /stacks` per board | `838 ms` |
| Concurrent `get_assigned_cards()`, three runs | `546 ms`, `348 ms`, `287 ms` |
| All-boards result as JSON, full cards | about `53 KB` |
| All-boards result as JSON, `compact=true` | about `7.5 KB` |

The first concurrent run includes connection setup, so the later runs are the better steady-state figure. Compact output matters more for agents than the latency gain: it cuts the tokens spent on each cross-board search by roughly 85 percent.

We also checked `GET /boards/{id}/stacks/{id}` as a cheaper way to read one stack for `list_cards`. It returns the same cards, but with `labels` set to `null` and `owner` as a plain string. Using it would silently drop labels, so `list_cards` keeps reading the stack list.

## Caching assessment

We checked safe cache-related response headers on the live API. This was a header-only check; it did not record host names, user names, board IDs, or card content.

| Endpoint shape | ETag | Last-Modified | Cache-Control | Conditional request |
| --- | --- | --- | --- | --- |
| Boards list | Present | Not present | `no-cache, no-store, must-revalidate` | `If-None-Match` returned `304` |
| Test board stacks | Not present | Not present | `no-cache, no-store, must-revalidate` | Not applicable |

Conditional revalidation is possible for `list_boards`, but broad caching would be premature. Stacks are the larger payload for most workflows, and the live stacks endpoint did not expose an ETag in this run. We should revisit conditional board-list caching only if repeated broad scans become a real delay in daily use.

## Recommendations

We should keep the current implementation. The existing shared `httpx.AsyncClient`, two-call `move_card` normal path, and straightforward Pydantic validation all measure well enough for this server's single-user MCP scope.

We should keep live mutation timing behind `DECK_TEST_BOARD_ID`. That rule prevents accidental writes to a real board while still allowing disposable-card performance checks when a test board is configured.

We should not add response caching in this phase. The current live latency is acceptable, and caching would add invalidation behavior that is more likely to create stale agent output than to improve user experience today.
