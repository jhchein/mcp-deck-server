# Decision: Comprehensive test strategy

**Date:** 2026-02-21
**Status:** Accepted

## Context

The server has zero tests. As the codebase restructures (decision 005) and the error contract changes (decision 002), we need a test suite that validates correctness, robustness under failure, and communication performance against the Nextcloud Deck API.

## Decision

### Test layers

1. **Unit tests** — per-module, fast, no network.
   - `test_config.py` — env var parsing, validation, defaults, missing-var errors.
   - `test_models.py` — Pydantic model validation against real Deck API response fixtures (captured JSON snapshots).
   - `test_client.py` — `make_nc_request` behavior: success, HTTP errors (4xx/5xx), timeouts, connection failures. Mock `httpx.AsyncClient` via `respx` or `pytest-httpx`.
   - `test_tools.py` — each MCP tool function: happy path, error propagation, edge cases (empty boards, archived cards, missing stacks).

2. **Integration tests** — optional, against a real Nextcloud instance.
   - Gated behind `--run-integration` marker or `DECK_INTEGRATION_TEST=1` env var.
   - Use a dedicated test board (created in setup, torn down after).
   - Validate full round-trip: create board → create stack → create card → update → move → archive → label operations.

3. **Communication robustness tests** — focused on network edge cases.
   - Timeout handling (server doesn't respond within configured timeout).
   - Connection reset / refused.
   - Malformed JSON responses.
   - HTTP 429 (rate limiting) if Nextcloud returns it.
   - Large response payloads (boards with many stacks/cards).
   - Concurrent tool calls (multiple tools invoked in parallel).

4. **Performance benchmarks** — lightweight, not blocking CI.
   - Measure httpx client reuse vs per-request creation (validates decision 001).
   - Measure `move_card` with stacks-response optimization vs N+1 (validates decision 003).
   - Use `pytest-benchmark` or simple timing assertions.
   - Run as a separate CI job or locally only — not in the main test gate.

### Test tooling

| Tool                      | Purpose                                                 |
| ------------------------- | ------------------------------------------------------- |
| `pytest`                  | Test runner                                             |
| `pytest-asyncio`          | Async test support                                      |
| `pytest-httpx` or `respx` | HTTP mocking (prefer `respx` — purpose-built for httpx) |
| `pytest-benchmark`        | Performance benchmarks (optional)                       |
| `pytest-cov`              | Coverage reporting                                      |

### Test directory layout

```
tests/
├── conftest.py           # Shared fixtures: mock client, test config, response factories
├── fixtures/             # JSON snapshots of real Deck API responses
│   ├── board.json
│   ├── boards_list.json
│   ├── stack.json
│   ├── card.json
│   └── ...
├── unit/
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_client.py
│   └── test_tools.py
├── integration/
│   ├── conftest.py       # Integration-specific fixtures (real NC connection)
│   └── test_deck_roundtrip.py
└── benchmarks/
    └── test_perf.py
```

### Fixture strategy

- Capture real Deck API JSON responses into `tests/fixtures/`.
- Build factory functions in `conftest.py` that return model instances from these fixtures.
- For mock HTTP, use `respx` to intercept httpx calls with canned fixture data.
- Integration tests use real credentials from env vars (never committed).

## Consequences

- High confidence in correctness before and after refactors.
- Robustness tests catch real-world failure modes (timeouts, bad responses).
- Performance benchmarks validate architectural decisions quantitatively.
- Integration tests are optional — CI runs unit tests only by default.
- Adds `respx`, `pytest`, `pytest-asyncio`, `pytest-cov` as dev dependencies.
