# Implementation Plan

Full execution plan for mcp-deck-server, derived from accepted decisions 001–011,
the agreed implementation plan from the architecture review, and the coherence
revision (decision 012).

## Agreed Parameters

| Parameter                | Value                                       | Source         |
| ------------------------ | ------------------------------------------- | -------------- |
| Type checker             | pyright                                     | User selection |
| Unit test coverage gate  | 90%                                         | User selection |
| SSE documentation policy | Undocumented until security review sign-off | User selection |
| CI integration tests     | On `main` + manual trigger (secrets-gated)  | User selection |
| CI benchmarks            | Non-blocking, `main`/manual only            | Decision 007   |

## Architecture Principles (from revision 012)

1. **Flat package layout** — `mcp_deck_server/` at repo root. Not `src/` layout. This project is a personal MCP server, not a PyPI-published library; the `src/` layout's import protection is not worth the configuration overhead.
2. **Tool independence** — tool functions call `make_nc_request` directly, never other tool functions. This decouples tools for independent testing and avoids hidden call-chain complexity.
3. **No throwaway intermediate states** — restructure and behavior fixes happen in one pass to avoid writing code that is immediately deleted.
4. **Fix confirmed problems, defer predicted ones** — changes like `archive_card` full-payload are conditional on API validation, not assumed.
5. **Proportionate tooling** — prefer simple solutions (e.g., `time.perf_counter`) over specialized libraries (`pytest-benchmark`) unless proven necessary.

---

## Phase 1 — Restructure & Fix

**Goal:** Establish the package layout AND implement core architectural improvements in a single pass: shared client, exception-based errors, behavior fixes.
**Decisions:** 001, 002, 003, 004, 005
**Depends on:** Nothing (first commit)

### Deliverables

| File                              | Purpose                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------- |
| `mcp_deck_server/__init__.py`    | Package init; re-exports `mcp` instance for `main.py`                        |
| `mcp_deck_server/config.py`      | `DeckConfig` frozen dataclass + env-var loader/validator                     |
| `mcp_deck_server/models.py`      | Pydantic models: `Owner`, `Label`, `Card`, `Stack`, `Board`                  |
| `mcp_deck_server/client.py`      | `make_nc_request` + `DeckAPIError` / `DeckHTTPError` / `DeckConnectionError` |
| `mcp_deck_server/server.py`      | `FastMCP("deck")` instance, lifespan hook, all `@mcp.tool()` registrations   |
| `main.py`                        | Thin entrypoint: `from mcp_deck_server.server import mcp; mcp.run()`         |
| `pyproject.toml`                 | Updated: dev dependency groups, tool configs                                 |

### Module dependency constraints

```
config.py  ←──  client.py  ←──  server.py  ←──  main.py
models.py  ←──  client.py
models.py  ←──  server.py
```

- `config.py` — zero intra-project imports (leaf)
- `models.py` — zero intra-project imports (leaf)
- `client.py` — imports `config`, `models` only
- `server.py` — composition root; imports `client`, `models`, `config`

### Tasks

#### 1a. Package structure

1. Create `mcp_deck_server/` directory with `__init__.py`.
2. Extract Pydantic models (`Owner`, `Label`, `Card`, `Stack`, `Board`) into `models.py`.
3. Create `config.py` with `DeckConfig` dataclass and `load_config()` function.
   - Required env vars: `NC_URL`, `NC_USER`, `NC_APP_PASSWORD`.
   - Optional: `NC_API_VERSION` (default `"v1.1"`), `MCP_TRANSPORT` (default `"stdio"`), `MCP_REQUEST_TIMEOUT` (default `30.0`).
   - `load_config()` raises `ValueError` immediately if required vars are missing.
   - Strip trailing slash from `NC_URL`.
   - Validate `MCP_TRANSPORT` is `"stdio"` or `"sse"`.
4. Replace `main.py` with thin entrypoint.
5. Update `pyproject.toml`:
   - Add `[dependency-groups]` section for dev deps.
   - Add `[tool.ruff]`, `[tool.pyright]`, `[tool.pytest.ini_options]` configs.

#### 1b. Lifespan + shared httpx client (Decision 001)

1. In `server.py`, implement a FastMCP `lifespan` context manager that:
   - Calls `load_config()` to get a validated `DeckConfig`.
   - Creates a single `httpx.AsyncClient` with `timeout=config.request_timeout` and auth/headers baked in.
   - Yields the client + config into the MCP context.
   - Closes the client on shutdown.
2. `make_nc_request` in `client.py` accepts the httpx client as a parameter (injected from lifespan context).
3. No module-level `NC_URL`, `NC_USER`, `NC_APP_PASSWORD`, `auth`, `headers` globals.

#### 1c. Exception contract (Decision 002)

Write `client.py` with the exception hierarchy from the start — no intermediate error-dict version.

1. Define in `client.py`:
   ```python
   class DeckAPIError(Exception): ...
   class DeckHTTPError(DeckAPIError):
       def __init__(self, status_code: int, body: str): ...
   class DeckConnectionError(DeckAPIError):
       def __init__(self, message: str): ...
   ```
2. `make_nc_request`:
   - Raises `DeckHTTPError` on `httpx.HTTPStatusError` (wrapping status code + response text).
   - Raises `DeckConnectionError` on `httpx.RequestError` / `httpx.TimeoutException`.
   - Returns only successful response data (JSON-parsed or `None` for 204).
3. No `isinstance(response, dict) and "error" in response` guards in any tool function.
4. Tools handle only the success path; FastMCP surfaces exceptions to the MCP client.

#### 1d. Tool independence convention

Tool functions call `make_nc_request` directly, never other tool functions:

1. `update_card` fetches the current card via `make_nc_request("GET", ...)` + `Card.model_validate()` inline — not via `get_card()`.
2. `move_card` fetches stacks via `make_nc_request("GET", ...)` + list comprehension — not via `list_stacks()`.
3. No tool function calls another tool function. This costs a few duplicated lines of `model_validate()` but eliminates tool→tool coupling for testing.

#### 1e. `move_card` N+1 fix (Decision 003)

1. Rewrite `move_card` to use `stacks[].cards[]` from the stacks GET response (the Nextcloud `/boards/{id}/stacks` endpoint returns cards embedded in each stack).
2. Remove the per-stack `list_cards` loop.
3. Result: 1 GET (stacks with embedded cards) + 1 PUT (reorder).
4. **Contingency:** If API investigation (Phase 2a) reveals that stacks don't embed cards, fall back to a GET-stacks + GET-cards-per-stack approach but document the limitation.

#### 1f. `archive_card` — defer full-payload fix

The current `{"archived": True}` payload may or may not blank other fields — this is unverified.

1. Keep the current `{"archived": True}` payload for now.
2. Mark with a `# TODO: validate whether partial PUT blanks fields (see Phase 2a)` comment.
3. If Phase 2 fixture capture shows the Deck API requires full payloads on PUT, add the fetch-merge-send pattern then.

#### 1g. Transport configuration (Decision 004)

1. In `main.py`, read `config.transport` and pass it to `mcp.run(transport=...)`.
2. Fail fast with a clear error if transport value is unrecognized.

#### 1h. `update_card` parameter rename

1. Rename the `type` parameter to `card_type` in `update_card`.
2. Map `card_type` back to `"type"` in the API payload.

### Acceptance Criteria

- [ ] `uv run main.py` starts the MCP server and responds to MCP protocol.
- [ ] All imports resolve; no circular dependencies.
- [ ] Module dependency constraints are satisfied.
- [ ] No tool function contains error-dict guard logic.
- [ ] No tool function calls another tool function.
- [ ] Startup fails immediately with `ValueError` if required env vars are missing.
- [ ] `move_card` performs exactly 1 GET + 1 PUT (verify via request log or mock).
- [ ] `MCP_TRANSPORT=stdio` starts stdio; `MCP_TRANSPORT=sse` starts SSE; invalid value fails with clear error.
- [ ] `update_card` accepts `card_type` parameter (not `type`).
- [ ] Existing tool names and signatures unchanged (except `type` → `card_type`).

### Verification

```bash
uv sync
uv run main.py                         # should start and respond to MCP protocol

# Startup validation
NC_URL= uv run main.py                # should fail with "NC_URL required"

# Transport
MCP_TRANSPORT=invalid uv run main.py   # should fail with "unrecognized transport"
```

---

## Phase 2 — Tests & Fixtures

**Goal:** Comprehensive test coverage: unit, robustness, integration. Includes API investigation via fixture capture (formerly Phase 3).
**Decisions:** 006, 008
**Depends on:** Phase 1

### Directory Layout

```
tests/
├── conftest.py               # Shared fixtures, response factories
├── fixtures/                  # JSON response snapshots (captured from live API or docs)
│   ├── board.json
│   ├── boards_list.json
│   ├── ...
│   └── error_404.json
├── unit/
│   ├── test_config.py         # DeckConfig loading/validation
│   ├── test_models.py         # Pydantic models against fixtures
│   ├── test_client.py         # make_nc_request: success, errors, timeouts
│   └── test_tools.py          # Each tool: happy path, errors, edge cases
├── integration/
│   ├── conftest.py            # Real Nextcloud connection fixtures
│   └── test_deck_roundtrip.py # Full CRUD round-trip
└── test_timing.py             # Simple timing validations (replaces pytest-benchmark)
```

### Tasks

#### 2a. API investigation & fixture capture (was standalone Phase 3)

1. **Research** the Deck API using:
   - Official docs: `https://deck.readthedocs.io/en/latest/API/`
   - Nextcloud Deck GitHub source: `https://github.com/nextcloud/deck`
   - Live API responses from a running instance.

2. **Key questions to resolve:**

   | Question                                              | Impacts                                  |
   | ----------------------------------------------------- | ---------------------------------------- |
   | Does `/boards/{id}/stacks` embed cards in response?   | `move_card` N+1 fix (Phase 1e)           |
   | Does PUT with partial payload blank omitted fields?   | `archive_card` fix (Phase 1f deferred)   |
   | What error HTTP codes + body shapes does Deck return? | Exception handling, test assertions       |
   | Does any endpoint paginate?                           | Tool signatures, completeness guarantees |
   | Do ETags work for caching?                            | P2 performance optimization              |
   | Are there assign/unassign user endpoints?             | Potential new tools                      |

   Remaining investigation areas (endpoints, permissions, rate limiting, board types) are documented inline in `docs/deck-api-reference.md` during Phase 6.

3. **Capture fixtures** — save real API JSON responses into `tests/fixtures/`:
   - `board.json`, `boards_list.json`
   - `stack.json`, `stacks_list.json`
   - `card.json`, `cards_list.json`
   - `card_create_response.json`, `card_update_response.json`
   - `card_reorder_response.json`
   - `label_assign_response.json`, `label_remove_response.json`
   - `error_404.json`, `error_403.json`, `error_400.json`
   - Each fixture includes metadata header: `{ "_meta": { "nc_version": "...", "deck_version": "...", "captured": "..." } }`

4. **Model validation report** — diff current Pydantic models against actual API responses:
   - Fields to add, fields to correct (wrong type), fields safe to ignore.
   - Apply corrections to `mcp_deck_server/models.py`.

5. **Retroactive Phase 1 fixes** — if fixture capture reveals:
   - Stacks don't embed cards → adjust `move_card` implementation.
   - Partial PUT blanks fields → add fetch-merge pattern to `archive_card`.

6. **Recommend** new tools to expose (if any) → add as P2 items in `todos.md`.

#### 2b. Test infrastructure

1. Add dev dependencies to `pyproject.toml`:
   ```
   pytest, pytest-asyncio, respx, pytest-cov
   ```
   (No `pytest-benchmark` — timing tests use `time.perf_counter` directly.)
2. Create `tests/conftest.py` with shared fixtures:
   - `test_config` — returns a `DeckConfig` with test values.
   - `mock_nc_client` — `respx`-mocked `httpx.AsyncClient`.
   - `load_fixture(name)` — reads JSON from `tests/fixtures/`.
   - Response factories — `make_board()`, `make_stack()`, `make_card()` returning model instances.
3. Configure `pyproject.toml` pytest settings:
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   testpaths = ["tests"]
   markers = ["integration: requires live Nextcloud instance", "slow: timing/performance tests"]
   ```

#### 2c. Unit tests

**`test_config.py`:**

- Valid env vars → `DeckConfig` with correct values.
- Missing required var → `ValueError` with specific message.
- Optional vars use defaults when absent.
- `NC_URL` trailing slash is stripped.
- Invalid `MCP_TRANSPORT` value → `ValueError`.
- Non-numeric `MCP_REQUEST_TIMEOUT` → `ValueError`.

**`test_models.py`:**

- Each model validates against its JSON fixture.
- Sparse responses (missing fields) validate without errors.
- Mixed-type fields (`owner` as `str` or `Owner`) handled correctly.
- Unknown extra fields are ignored (or rejected — match Pydantic config).

**`test_client.py`:**

- Successful GET → returns parsed JSON.
- Successful POST with payload → returns parsed JSON.
- 204 No Content → returns `None`.
- HTTP 4xx → raises `DeckHTTPError` with correct `.status_code` and `.body`.
- HTTP 5xx → raises `DeckHTTPError`.
- Connection refused → raises `DeckConnectionError`.
- Timeout → raises `DeckConnectionError`.
- Malformed JSON response → raises appropriate error.

**`test_tools.py`:**

Because tools call `make_nc_request` directly (not each other), each tool can be tested in isolation with `respx`:

- For each of the 11 tools:
  - Happy path: mock API returns fixture → tool returns correct model.
  - API error: mock API returns 404 → tool raises `DeckHTTPError`.
  - Edge cases per tool:
    - `list_boards` with empty list.
    - `move_card` with target stack not found → `ValueError`.
    - `move_card` with card not found → `ValueError`.
    - `update_card` with no optional params (uses current card values).
    - `archive_card` — validate behavior matches API contract.

#### 2d. Communication robustness tests

Add to `test_client.py` or a dedicated `test_robustness.py`:

| Scenario                                                   | Expected behavior                                   |
| ---------------------------------------------------------- | --------------------------------------------------- |
| Timeout (server doesn't respond within configured timeout) | `DeckConnectionError` raised promptly               |
| Connection reset mid-response                              | `DeckConnectionError` raised                        |
| Malformed JSON body (valid HTTP 200)                       | Error raised (not a silent parse failure)           |
| HTTP 429 Too Many Requests                                 | `DeckHTTPError` with `.status_code == 429`          |
| Very large response (board with 1000 cards)                | Parses successfully within timeout                  |
| Concurrent tool calls                                      | All complete without corrupting shared client state |

#### 2e. Integration tests

**`test_deck_roundtrip.py`:**

- Gated behind `@pytest.mark.integration` marker.
- Requires `NC_URL`, `NC_USER`, `NC_APP_PASSWORD` env vars (skip if absent).
- Full round-trip:
  1. `list_boards` → pick or create a test board.
  2. `list_stacks` → pick or create a test stack.
  3. `create_card` → verify returned `Card`.
  4. `get_card` → verify matches created card.
  5. `update_card` → change title/description, verify.
  6. `assign_label_to_card` → verify.
  7. `remove_label_from_card` → verify.
  8. `move_card` → verify card is in new stack.
  9. `archive_card` → verify `archived == True`.
  10. Cleanup: delete test card/board if created.

#### 2f. Simple timing tests (replaces pytest-benchmark)

**`test_timing.py`:**

- Shared client vs per-request client — measure wall-clock time for 10 sequential requests using `time.perf_counter`.
- `move_card` optimized (stacks response) vs N+1 (simulated) — measure call count and wall-clock time.
- Results printed with `-s` flag; assertions are coarse (e.g., shared client is faster, optimized `move_card` makes fewer calls).
- Marked `@pytest.mark.slow` — not part of normal test run.

### Acceptance Criteria

- [ ] `pytest tests/unit/ --cov=mcp_deck_server --cov-fail-under=90` passes.
- [ ] Every endpoint we use has at least one captured fixture (success + error).
- [ ] Error codes/body patterns documented for each endpoint.
- [ ] Model validation diff is complete — no unknown gaps.
- [ ] Integration tests skip cleanly when env vars are absent.
- [ ] All robustness scenarios have a test that verifies the expected error type.
- [ ] Timing tests run without failures (results informational).

### Verification

```bash
uv sync --dev
pytest tests/unit/ --cov=mcp_deck_server --cov-report=term-missing --cov-fail-under=90
pytest tests/integration/ -m integration  # optional, needs credentials
pytest tests/test_timing.py -s            # informational
```

---

## Phase 3 — CI Pipeline

**Goal:** Automated quality gates on every PR.
**Decisions:** 007
**Depends on:** Phase 2 (tests exist and pass locally)

### Workflow: `.github/workflows/ci.yml`

```yaml
# Conceptual structure — not literal YAML
name: CI

on:
  push: { branches: [main] }
  pull_request: { branches: [main] }
  workflow_dispatch: {}

jobs:
  lint:
    # ruff check + ruff format --check + pyright
    # Runs on: every push and PR

  test:
    needs: lint
    # uv sync --dev
    # pytest tests/unit/ --cov --cov-fail-under=90 --cov-report=xml
    # Upload coverage artifact
    # Runs on: every push and PR

  integration:
    needs: test
    if: github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'
    # pytest tests/integration/ -m integration
    # Requires: NC_URL, NC_USER, NC_APP_PASSWORD as Actions secrets
    # Skips gracefully if secrets absent

  benchmarks:
    needs: test
    if: github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'
    # pytest tests/test_timing.py -s
    # Informational — does not block merge

  audit:
    # uv audit (or pip-audit)
    # Can be blocking or non-blocking — recommend blocking
```

### Tasks

1. Create `.github/workflows/ci.yml` with the above structure.
2. Configure GitHub Actions to use `uv` for dependency management.
3. Set up Python 3.13 in the matrix.
4. Configure `pyright` (add `pyrightconfig.json` or `[tool.pyright]` in `pyproject.toml`).
5. Add `ruff` config to `pyproject.toml` (`[tool.ruff]`).
6. Add coverage artifact upload step.

### pyproject.toml additions

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "respx>=0.22",
    "ruff>=0.8",
    "pyright>=1.1",
]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.pyright]
pythonVersion = "3.13"
typeCheckingMode = "standard"
venvPath = "."
venv = ".venv"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["integration: requires live Nextcloud instance", "slow: timing/performance tests"]
```

### Acceptance Criteria

- [ ] PR to `main` blocked on lint + pyright + unit tests + 90% coverage.
- [ ] Integration/benchmark jobs are non-blocking and skip safely without secrets.
- [ ] Dependency audit runs (blocking).

---

## Phase 4 — Security Review

**Goal:** Identify and rate security risks; produce durable documentation; block SSE until resolved.
**Decisions:** 010
**Depends on:** Phase 1 (review the actual refactored implementation)
**Can run in parallel with:** Phase 2, Phase 3

### Review Scope

| Area                      | What to assess                                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Credential handling       | How are `NC_URL`, `NC_USER`, `NC_APP_PASSWORD` loaded, stored in memory, used? Leak vectors via errors, logs, MCP responses? |
| Input validation          | Are tool parameters validated before URL interpolation? Path traversal via `board_id`? Injection via `title`/`description`?  |
| SSRF risk                 | Can a malicious MCP client craft parameters that cause requests to arbitrary URLs? (`NC_URL` is user-controlled.)            |
| Transport security        | stdio = local-only (trusted). SSE = HTTP endpoint — what auth/binding is needed?                                             |
| Dependency audit          | Are deps pinned via `uv.lock`? Known CVEs in `httpx`, `mcp-server`, `pydantic`, `python-dotenv`?                             |
| Error information leakage | Do error messages expose internal URLs, credentials, or stack traces to MCP clients?                                         |
| App password scope        | What Nextcloud permissions does an app password grant? Is it scoped to Deck?                                                 |

### Tasks

1. Audit each area above against the refactored codebase.
2. Rate each finding: **Low / Medium / High / Critical**.
3. Write `docs/security.md` with findings, ratings, and recommendations.
4. File remediation items in `project-spec/todos.md`:
   - Critical/High → P0
   - Medium → P1
   - Low → P2
5. Validate that `NC_URL` is validated as a proper base URL at config time.
6. Validate that integer parameters (`board_id`, etc.) are type-enforced by FastMCP/Pydantic before reaching tool code.
7. Confirm `uv.lock` is committed and add `uv audit` to CI.
8. Define SSE ship/no-ship criteria (what must be true before SSE is documented).

### Deliverables

| File                       | Purpose                                         |
| -------------------------- | ----------------------------------------------- |
| `docs/security.md`         | Security review findings and recommendations    |
| `project-spec/todos.md`    | Remediation items added at appropriate priority |
| `.github/workflows/ci.yml` | `uv audit` step added if not already present    |

### Acceptance Criteria

- [ ] Every review area has a documented finding and risk rating.
- [ ] No Critical or unmitigated High findings remain open.
- [ ] SSE ship criteria are explicitly defined and documented.

---

## Phase 5 — Performance Review

**Goal:** Quantitative evidence for architectural decisions; baseline metrics; caching recommendations.
**Decisions:** 011
**Depends on:** Phase 1 (shared client + move_card fix implemented), Phase 2f (timing tests)

### Review Scope

| Area                     | What to measure                                                      |
| ------------------------ | -------------------------------------------------------------------- |
| Connection overhead      | Per-request client vs shared client — TCP + TLS handshake cost       |
| `move_card` optimization | Old N+1 vs new stacks-response approach — wall-clock, API call count |
| Response parsing         | Pydantic `model_validate` cost for large payloads (100+ cards)       |
| Timeout behavior         | Does the 30s timeout surface promptly or does something hang?        |
| Concurrency              | Multiple tools called in parallel — correctness and throughput       |
| Payload size             | Typical response sizes for boards/stacks/cards                       |
| Caching potential        | ETags or short-lived caches for `list_boards`/`list_stacks`          |

### Tasks

1. Run timing tests from Phase 2f.
2. Analyze results and document findings.
3. If caching is warranted, propose a design (but do not implement — P2).
4. Write `docs/performance.md` with findings, metrics, and recommendations.
5. File optimization items in `todos.md` (P2 unless something is egregiously slow).

### Deliverables

| File                    | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `docs/performance.md`   | Performance review findings and baseline metrics     |
| `project-spec/todos.md` | Optimization recommendations at appropriate priority |

### Acceptance Criteria

- [ ] Shared client demonstrates measurable improvement over per-request.
- [ ] `move_card` optimization shows reduced API call count.
- [ ] No unexpected performance cliff found.

---

## Phase 6 — Documentation

**Goal:** Complete, accurate, user-facing documentation.
**Decisions:** 009
**Depends on:** All prior phases (documents findings from security and performance reviews)

### Deliverables

| File                         | Purpose                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| `README.md`                  | One-liner, quick start (3 steps), tooling badges, links to `docs/`   |
| `docs/setup.md`              | Installation, env var configuration, first run, troubleshooting      |
| `docs/usage.md`              | How to connect MCP clients (Claude Desktop, VS Code, Cursor, etc.)   |
| `docs/tools-reference.md`    | Every MCP tool: description, parameters, return type, example        |
| `docs/architecture.md`       | Module layout, dependency graph, decisions summary, design rationale |
| `docs/deck-api-reference.md` | (From Phase 2a) Upstream API investigation results                   |
| `docs/security.md`           | (From Phase 4) Security review findings                              |
| `docs/performance.md`        | (From Phase 5) Performance review findings                           |

### Tasks

1. Write `README.md`:
   - Project name and one-liner.
   - Quick start: clone → configure `.env` → `uv run main.py`.
   - Link to `docs/tools-reference.md` for tool catalog.
   - Badge placeholders: CI status, coverage.
   - **Do NOT document SSE transport** (per agreed policy).
2. Write `docs/setup.md`:
   - Prerequisites: Python 3.13+, uv.
   - Clone, `uv sync`, configure `.env`.
   - Environment variable reference table.
   - First run instructions.
   - Troubleshooting: common errors and fixes.
3. Write `docs/usage.md`:
   - MCP client configuration for Claude Desktop (`claude_desktop_config.json`).
   - VS Code MCP extension configuration.
   - Cursor configuration.
   - Example prompts that exercise tools.
4. Write `docs/tools-reference.md`:
   - For each of the 11 tools: name, description, parameters (with types and defaults), return type, example request/response.
   - Keep in sync with actual tool registrations in `server.py`.
5. Write `docs/architecture.md`:
   - Module dependency diagram.
   - Module responsibilities table.
   - Lifespan lifecycle explanation.
   - Error flow: exception hierarchy → FastMCP → MCP client.
   - Summary of key decisions (link to `project-spec/decisions/`).

### Acceptance Criteria

- [ ] README quick-start works end-to-end on a clean clone.
- [ ] Every tool has a reference entry matching its actual signature.
- [ ] No mention of SSE transport in user-facing docs.
- [ ] All internal links resolve (no broken doc links).

---

## Phase 7 — Spec Consistency Pass

**Goal:** Update all project-spec files to reflect the implemented state.
**Depends on:** All prior phases complete.

### Tasks

1. Update `project-spec/project.md` — confirm goals are met, fill in non-goals if determined.
2. Update `project-spec/interfaces.md` — reflect any model changes from Phase 2a and any new tools.
3. Update `project-spec/infrastructure.md` — reflect final CI configuration.
4. Update `project-spec/constraints.md` — add any security constraints from Phase 4.
5. Update `project-spec/todos.md` — close completed items, ensure remediation/optimization items from reviews are captured.
6. Update `.github/instructions/python.instructions.md` — reflect any convention changes discovered during implementation.

### Acceptance Criteria

- [ ] No stale `_TBD_` entries remain for implemented features.
- [ ] Todos reflect current reality (no phantom items, no missing items).

---

## Dependency Graph

```
Phase 1 (restructure & fix)
  │
  ├──► Phase 2 (tests & fixtures)  ──► Phase 3 (CI)
  │
  ├──► Phase 4 (security review)
  │
  └──► Phase 5 (performance review)

Phase 6 (documentation) — after Phases 2, 4, 5

Phase 7 (spec consistency) — after all
```

**Parallelization opportunities:**

- Phase 4 can start as soon as Phase 1 completes (in parallel with Phase 2).
- Phase 5 depends on Phase 1 code + Phase 2f timing tests.
- Phase 6 can be drafted continuously, finalized after Phases 2, 4, 5.

---

## Open Risks

| Risk                                                                         | Mitigation                                                              |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Non-goals still TBD — scope creep during API investigation                   | Define non-goals before starting Phase 2a                               |
| Stacks endpoint may not embed cards                                          | Phase 2a validates; Phase 1e has contingency plan                       |
| Fixture freshness — Nextcloud version differences may invalidate schemas     | Include version metadata in fixtures; re-capture on NC upgrades         |
| Integration test environment — who provisions the test instance and secrets? | Document requirement; skip gracefully in CI when absent                 |
| SSE security criteria underdefined                                           | Phase 4 must produce explicit ship/no-ship criteria                     |
| `pyright` standard mode may flag Pydantic `Optional[Union[...]]` patterns    | Use `typeCheckingMode = "standard"` (not strict); address incrementally |

---

## Note on Decision Records

Decisions 001–005 are genuine architectural decisions with alternatives considered — they belong in the decision log. Decisions 006–011 are planned work items (testing, CI, docs, security review, performance review, API investigation). They are retained as historical record but future ADRs should reserve the format for choices where alternatives were evaluated and rejected.

---

## Verification Checklist (End-to-End)

```bash
# 1. Dependencies
uv sync --dev

# 2. Lint + format
ruff check .
ruff format --check .

# 3. Type check
pyright

# 4. Unit tests + coverage
pytest tests/unit/ --cov=mcp_deck_server --cov-report=term-missing --cov-fail-under=90

# 5. Integration (optional — needs credentials)
pytest tests/integration/ -m integration

# 6. Timing tests (informational)
pytest tests/test_timing.py -s

# 7. Dependency audit
uv audit

# 8. Manual smoke
uv run main.py                         # stdio — should start
NC_URL= uv run main.py                # should fail: missing config
MCP_TRANSPORT=invalid uv run main.py   # should fail: bad transport
```
