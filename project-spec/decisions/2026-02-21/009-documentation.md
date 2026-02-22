# Decision: Documentation in `docs/`

**Date:** 2026-02-21
**Status:** Accepted

## Context

The project has an empty README and no documentation. Users, contributors, and the maintainer's future self all need clear guidance.

## Decision

### Documentation structure

```
docs/
├── setup.md                # Installation, env var config, first run
├── usage.md                # How to connect MCP clients (Claude Desktop, VS Code, etc.)
├── tools-reference.md      # Every MCP tool: description, params, return shapes, examples
├── deck-api-reference.md   # Upstream API investigation results (from decision 008)
├── architecture.md         # Module layout, dependency graph, design decisions summary
├── security.md             # Security review findings and recommendations
└── performance.md          # Performance review findings and recommendations
```

### README.md

Short and actionable:

- One-liner description
- Quick start (3 steps: clone, configure `.env`, `uv run main.py`)
- Link to `docs/` for details
- Link to `docs/tools-reference.md` for tool catalog
- Badge placeholders for CI status and coverage

### Approach

- Write for the "new contributor in 5 minutes" persona.
- Keep `docs/` as plain Markdown — no static site generator unless the project grows significantly.
- `docs/tools-reference.md` should be generated or kept in sync with the actual tool registrations in `server.py`.
- `docs/architecture.md` summarizes the decisions in `project-spec/decisions/` in a more readable format.

## Consequences

- Clear onboarding path for users and contributors.
- Security and performance reviews produce durable, referenceable artifacts (not just one-time audits).
- `docs/` is versioned alongside the code.
- README becomes the entry point, `docs/` has the depth.
