# ToDos

## ~~Phase 1: Restructure & Fix~~ ✅

All P0 items complete:

- [x] Restructure to `mcp_deck_server/` flat package layout (decision 005)
- [x] Implement lifespan hook with shared httpx client + config validation (decision 001)
- [x] Refactor `make_nc_request` to raise exceptions instead of returning error dicts (decision 002)
- [x] Enforce tool independence: tools call `make_nc_request`, never other tools (decision 012)
- [x] Fix `move_card` N+1 query — use stacks response cards directly (decision 003)
- [x] Make transport configurable via `MCP_TRANSPORT` env var (decision 004)
- [x] Rename `update_card` `type` parameter to `card_type` (shadows builtin)
- [x] Refactor `update_card` payload: `None`=keep, `""`=clear convention (decision 012)

## Phase 2: Tests & Fixtures (decisions 006, 008) — in progress

Done:

- [x] Add dev dependencies: `pytest`, `pytest-asyncio`, `respx`, `pytest-cov`
- [x] Create `tests/` directory structure (unit, fixtures, helpers)
- [x] Write `tests/conftest.py` with shared fixtures (mock client, test config, response factories)
- [x] Capture response fixtures into `tests/fixtures/` (board, card, stacks_list, errors, reorder)
- [x] Write `tests/unit/test_config.py` — env var parsing, validation, missing vars
- [x] Write `tests/unit/test_models.py` — Pydantic models against fixture data
- [x] Write `tests/unit/test_client.py` — `make_nc_request` success, HTTP errors, timeouts, connection failures
- [x] Write `tests/unit/test_tools.py` — comprehensive tool coverage (50 unit tests total): happy paths, error branches, edge cases
- [x] Coverage gate: 99.65% total, `server.py` at 100%

Remaining:

- [x] Research official Deck API docs and source; resolve key questions (decision 013: stacks embed cards ✓, full PUT confirmed ✓, no archive endpoint documented)
- [x] Define non-goals explicitly in `project-spec/project.md`
- [x] Identify new endpoints/tools → `assignUser`/`unassignUser` promoted; comments/attachments/CRUD scoped as non-goals
- [x] Apply model corrections: rename `Owner.displayName` → `displayname`, narrow `Board.settings` to `dict | None`
- [x] Validate Pydantic models against actual API responses (live instance); apply further corrections (decision 014)
- [x] Add `assign_user_to_card` and `unassign_user_from_card` tools
- [x] Write communication robustness tests — malformed JSON, large payloads, concurrent calls
- [x] Scaffold `tests/integration/test_deck_roundtrip.py` — full CRUD round-trip (marker-gated)
- [x] Scaffold `tests/test_timing.py` — client reuse vs per-request, move_card optimization (`time.perf_counter`)

## Phase 3: CI pipeline (decision 007) — in progress

Done:

- [x] Add dev dependencies: `ruff`, `pyright`
- [x] Create `.github/workflows/ci.yml` with lint + test + integration + benchmarks + audit jobs
- [x] Configure coverage reporting (xml artifact + term-missing, gate at 80%)
- [x] Add optional integration test job (secrets-gated, graceful skip)
- [x] Add audit job (`uv audit`)

Remaining:

- [ ] Configure GitHub branch protection on `main` with required checks: `lint`, `test`, `audit`
- [ ] Require pull request before merge on `main` with at least 1 approval
- [ ] Enable branch protection policy: require branches to be up to date before merge
- [ ] Enable branch protection policy: dismiss stale approvals when new commits are pushed

## Phase 4: Security review (decision 010)

- [ ] Review credential handling (load, storage, leak vectors)
- [ ] Review input validation (URL interpolation, SSRF risk)
- [ ] Review transport security (stdio vs SSE exposure surface)
- [ ] Audit dependencies for known CVEs (`uv audit` or equivalent)
- [ ] Review error information leakage to MCP clients
- [ ] Investigate Nextcloud app password scope
- [ ] Write `docs/security.md` with findings and recommendations
- [ ] File remediation items as P0/P1 todos

## Phase 5: Performance review (decision 011)

- [ ] Measure connection overhead: per-request vs shared client
- [ ] Measure `move_card` N+1 vs stacks-response optimization
- [ ] Measure Pydantic `model_validate` cost for large payloads
- [ ] Assess timeout behavior under slow Nextcloud responses
- [ ] Test concurrent tool call behavior
- [ ] Evaluate caching potential (ETags, short-lived caches)
- [ ] Write `docs/performance.md` with findings and recommendations
- [ ] Use simple `time.perf_counter` timing (from `tests/test_timing.py`), not `pytest-benchmark`

## Phase 6: Documentation (decision 009)

- [ ] Write `README.md` — one-liner, quick start, links to docs
- [ ] Write `docs/setup.md` — installation, env config, first run
- [ ] Write `docs/usage.md` — connecting MCP clients
- [ ] Write `docs/tools-reference.md` — tool catalog with params, returns, examples
- [ ] Write `docs/architecture.md` — module layout, dependency graph, decisions summary

## P2 (later)

- [ ] Consider publishing to MCP server registry
- [ ] Evaluate typed response models for `assign_label_to_card` / `remove_label_from_card` / user assignment tools
- [ ] Add `pre-commit` hooks for local dev experience
- [ ] Static site generator for docs (if project grows)
- [ ] Evaluate ETag caching for GET endpoints (Phase 5 finding)
- [ ] Comments API support (OCS base URL, pagination — currently a non-goal)
- [ ] Attachment management (multipart upload — currently a non-goal)
- [ ] Board/Stack/Label CRUD tools (currently a non-goal)
