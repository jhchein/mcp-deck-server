# Decision: Restructure to package layout

**Date:** 2026-02-21
**Status:** Accepted (amended by 012 — flat layout instead of `src/`)

## Context

The entire server lives in a single `main.py` (350 lines). With upcoming work (tests, SSE transport, lifespan-managed client), a single file will become unwieldy. Restructuring now avoids a disruptive refactor later.

## Decision

Adopt this layout:

```
mcp-deck-server/
├── mcp_deck_server/
│   ├── __init__.py        # Package init, re-exports mcp instance
│   ├── server.py          # FastMCP instance, lifespan hook, tool registration
│   ├── client.py          # make_nc_request, DeckAPIError hierarchy
│   ├── models.py          # Pydantic models (Board, Stack, Card, Label, Owner)
│   └── config.py          # Config dataclass, env var loading & validation
├── tests/
│   ├── conftest.py            # Fixtures (mock httpx client, test config)
│   └── test_tools.py          # Tool-level tests (placeholder)
├── main.py                    # Thin entrypoint: import and run
├── pyproject.toml
└── README.md
```

> **Note:** Originally proposed as `src/mcp_deck_server/`. Revised to flat `mcp_deck_server/` by decision 012 — the `src/` layout's import protection is not worth the configuration overhead for a personal tool.

### Module responsibilities

| Module      | Responsibility                                                                                                        |
| ----------- | --------------------------------------------------------------------------------------------------------------------- |
| `config.py` | Load env vars, validate, expose as a frozen dataclass. No I/O.                                                        |
| `models.py` | Pydantic models only. No business logic, no imports from other project modules.                                       |
| `client.py` | `make_nc_request` + exception classes. Depends on `config` and `models`.                                              |
| `server.py` | FastMCP instance, lifespan context manager, all `@mcp.tool()` registrations. Depends on `client`, `models`, `config`. |
| `main.py`   | `from mcp_deck_server.server import mcp; mcp.run()` — nothing else.                                                   |

### Constraints

- `models.py` must have zero intra-project imports (leaf module).
- `config.py` must have zero intra-project imports (leaf module).
- `client.py` depends on `config` and `models` only.
- `server.py` is the composition root — it wires everything together.

## Consequences

- Clear separation of concerns; each module is independently testable.
- Flat layout means no special `pyproject.toml` package discovery config needed.
- Existing `main.py` becomes a thin shim — no breakage for users running `uv run main.py`.
