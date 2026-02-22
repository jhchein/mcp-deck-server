# ToDos

## P0 (blockers) — Phase 1: Restructure & Fix

- Restructure to `mcp_deck_server/` flat package layout (decision 005)
- Implement lifespan hook with shared httpx client + config validation (decision 001)
- Refactor `make_nc_request` to raise exceptions instead of returning error dicts (decision 002)
- Enforce tool independence: tools call `make_nc_request`, never other tools (decision 012)
- Fix `move_card` N+1 query — use stacks response cards directly (decision 003)
- Make transport configurable via `MCP_TRANSPORT` env var (decision 004)
- Rename `update_card` `type` parameter to `card_type` (shadows builtin)

## P1 (next) — Phase 2: Tests & Fixtures (decisions 006, 008)

- Research official Deck API docs and source; resolve key questions (stacks embed cards? partial PUT behavior?)
- Capture real API response fixtures into `tests/fixtures/`
- Validate Pydantic models against actual API responses; apply corrections
- Add dev dependencies: `pytest`, `pytest-asyncio`, `respx`, `pytest-cov`
- Create `tests/` directory structure (unit, integration, benchmarks, fixtures)
- Write `tests/conftest.py` with shared fixtures (mock client, test config, response factories)
- Write `tests/unit/test_config.py` — env var parsing, validation, missing vars
- Write `tests/unit/test_models.py` — Pydantic models against fixture data
- Write `tests/unit/test_client.py` — `make_nc_request` success, HTTP errors, timeouts, connection failures
- Write `tests/unit/test_tools.py` — each tool: happy path, error propagation, edge cases (each tool testable in isolation due to tool independence)
- Write communication robustness tests — timeouts, connection resets, malformed JSON, large payloads, concurrent calls
- Write `tests/integration/test_deck_roundtrip.py` — full CRUD round-trip (gated behind marker)
- Write `tests/test_timing.py` — client reuse vs per-request, move_card optimization (simple `time.perf_counter`, no pytest-benchmark)
- If API investigation reveals: `archive_card` partial PUT blanks fields → add fetch-merge-send pattern
- If API investigation reveals: stacks don't embed cards → adjust `move_card` implementation
- Identify new endpoints/tools to add (comments, attachments, user assignment) → file as P2
- Define non-goals explicitly (before API investigation drives scope creep)

## P1 (next) — Phase 3: CI pipeline (decision 007)

- Add dev dependencies: `ruff`, `pyright`
- Create `.github/workflows/ci.yml` with lint + test jobs
- Configure coverage reporting
- Add optional integration test job (requires GitHub Actions secrets)

## P1 (next) — Phase 4: Security review (decision 010)

- Review credential handling (load, storage, leak vectors)
- Review input validation (URL interpolation, SSRF risk)
- Review transport security (stdio vs SSE exposure surface)
- Audit dependencies for known CVEs (`uv audit` or equivalent)
- Review error information leakage to MCP clients
- Investigate Nextcloud app password scope
- Write `docs/security.md` with findings and recommendations
- File remediation items as P0/P1 todos

## P1 (next) — Phase 5: Performance review (decision 011)

- Measure connection overhead: per-request vs shared client
- Measure `move_card` N+1 vs stacks-response optimization
- Measure Pydantic `model_validate` cost for large payloads
- Assess timeout behavior under slow Nextcloud responses
- Test concurrent tool call behavior
- Evaluate caching potential (ETags, short-lived caches)
- Write `docs/performance.md` with findings and recommendations
- Use simple `time.perf_counter` timing (from `tests/test_timing.py`), not `pytest-benchmark`

## P1 (next) — Phase 6: Documentation (decision 009)

- Write `README.md` — one-liner, quick start, links to docs
- Write `docs/setup.md` — installation, env config, first run
- Write `docs/usage.md` — connecting MCP clients
- Write `docs/tools-reference.md` — tool catalog with params, returns, examples
- Write `docs/architecture.md` — module layout, dependency graph, decisions summary

## P2 (later)

- Consider publishing to MCP server registry
- Evaluate typed response models for `assign_label_to_card` / `remove_label_from_card`
- Add `pre-commit` hooks for local dev experience
- Static site generator for docs (if project grows)
