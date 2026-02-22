# Infrastructure

How the system is deployed and operated.

## Runtime

- **Local**: `uv run main.py` — stdio transport, invoked by MCP clients (Claude Desktop, VS Code, etc.)
- **Remote**: SSE/HTTP transport — _TBD_ (planned; blocked on security review, decision 010)

## CI/CD

- **Platform**: GitHub Actions (decision 007)
- **Workflow**: `.github/workflows/ci.yml`
- **Jobs**: lint (ruff + pyright) → test (pytest unit + coverage) → integration (optional, secrets-gated) → benchmarks (optional, main-only)
- **Dev deps**: ruff, pyright, pytest, pytest-asyncio, respx, pytest-cov

## IaC

- N/A (single-process tool server, no cloud infrastructure yet)
