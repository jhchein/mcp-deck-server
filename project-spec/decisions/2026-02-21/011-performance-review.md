# Decision: Performance review

**Date:** 2026-02-21
**Status:** Accepted

## Context

MCP tool calls should feel fast to the LLM agent — slow tools degrade the user experience and may cause timeouts on the client side. A performance review is needed to identify bottlenecks and validate that the architectural decisions (shared client, N+1 fix) deliver measurable improvements.

## Decision

### Review scope

| Area                    | What to measure / assess                                                                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Connection overhead** | Per-request client creation vs shared client (decision 001). Measure TCP + TLS handshake cost.                                                                    |
| **N+1 in `move_card`**  | Current implementation vs stacks-response optimization (decision 003). Measure wall-clock time on a board with 5+ stacks.                                         |
| **Response parsing**    | Pydantic `model_validate` cost for large payloads (board with 100+ cards). Is it negligible or worth optimizing?                                                  |
| **Timeout behavior**    | How does the server behave when Nextcloud is slow? Does the 30s timeout (decision 001) surface promptly, or does it hang?                                         |
| **Concurrency**         | What happens when multiple tools are called in parallel (e.g., `list_boards` + `list_stacks`)? Does the shared httpx client handle concurrent requests correctly? |
| **Payload size**        | What's the typical response size for boards/stacks/cards? Are we transferring unnecessary data?                                                                   |
| **Caching potential**   | Can we use ETags or short-lived caches for `list_boards`/`list_stacks` to avoid redundant API calls within a session?                                             |

### Deliverables

1. **`docs/performance.md`** — findings, measurements, and recommendations.
2. **Benchmark tests** in `tests/benchmarks/` — codified measurements that can be re-run.
3. **Optimization recommendations** — filed as items in `todos.md`.

### What is NOT in scope

- Micro-optimizations (e.g., shaving milliseconds off JSON parsing).
- Nextcloud server-side performance tuning.
- Load testing for multi-user scenarios (server is single-user).

## Consequences

- Quantitative evidence for architectural decisions.
- Benchmarks can be re-run after changes to detect regressions.
- May surface caching opportunities that improve the LLM agent experience.
- Performance doc provides a baseline for future comparison.
