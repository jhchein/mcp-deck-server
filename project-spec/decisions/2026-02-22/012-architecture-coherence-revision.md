# Decision 012 — Architecture Coherence Revision

**Date:** 2026-02-22
**Status:** Accepted
**Supersedes:** Clarifies/amends 001–011

## Context

After documenting the full 9-phase implementation plan (decisions 001–011), a coherence review identified 7 issues ranging from wasted work to speculative fixes. The plan was individually reasonable per-decision but collectively over-engineered for a ~350-line personal MCP server.

## Revisions Applied

### 1. Merge Phase 1 + 2 → single "Restructure & Fix" (High impact)

**Problem:** Phase 1 would create `client.py` with the error-dict pattern, then Phase 2 would immediately delete it and write the exception version. No tests gate the intermediate state.

**Resolution:** Write `client.py` with exceptions from the start. One pass, no throwaway code.

### 2. Flat package layout instead of `src/` (Medium impact)

**Problem:** `src/mcp_deck_server/` is the standard layout for publishable PyPI packages. This project is run with `uv run main.py` — it's a personal tool, not a library. The `src/` layout adds configuration overhead and deeper nesting for no benefit.

**Resolution:** Use `mcp_deck_server/` at the repo root. Amends decision 005.

### 3. Tool independence convention (Medium impact)

**Problem:** `update_card` calls `get_card()`, `move_card` calls `list_stacks()` and `list_cards()` — tool→tool coupling. Testing requires mocking multi-hop call chains through `respx`.

**Resolution:** Tools call `make_nc_request` directly, never other tool functions. Costs a few lines of `model_validate()` duplication but each tool is independently testable.

### 4. `archive_card` fix deferred until validated (Medium impact)

**Problem:** The plan assumed partial PUT blanks omitted fields, prescribing a fetch-merge-send pattern. This is unverified.

**Resolution:** Keep `{"archived": True}` for now. Validate during API investigation (Phase 2a). Fix only if confirmed.

### 5. API Investigation folded into Test phase (Low-Medium)

**Problem:** Phase 3 was standalone research producing markdown and JSON — not code. It's test setup work, not a separate milestone.

**Resolution:** API investigation becomes sub-task 2a of the Tests & Fixtures phase.

### 6. Drop `pytest-benchmark` (Low impact)

**Problem:** Statistical benchmarking for a single-user MCP server is disproportionate. The two things to validate (shared client saves handshakes, `move_card` makes fewer calls) are coarse effects.

**Resolution:** Use `time.perf_counter` in simple timing tests marked `@pytest.mark.slow`.

### 7. ADR distinction acknowledged (Low impact)

**Problem:** Decisions 006–011 don't have meaningful alternatives — they record "we will do X" rather than "we chose X over Y because Z."

**Resolution:** No file changes. Retained as historical record. Future ADRs should record choices with rejected alternatives.

## Result

9 phases → 7 phases. Reduced configuration overhead, eliminated throwaway intermediate state, improved testability, deferred unvalidated fixes.
