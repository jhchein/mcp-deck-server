# Project

## Overview

- **Name**: mcp-deck-server
- **One-liner**: MCP tool server that lets AI agents manage Nextcloud Deck kanban boards.

## Goals

- Expose Nextcloud Deck board/stack/card/label operations as MCP tools
- Support both local stdio and remote SSE/HTTP transport
- Thoroughly tested with unit, integration, robustness, and performance tests
- Well-documented (setup, usage, tool reference, architecture, security, performance)
- Security-reviewed and hardened before remote transport is shipped
- Performance-validated against architectural decisions

## Non-goals

- **Comments API** — uses OCS base URL (`/ocs/v2.php/...`), has pagination, would require second client configuration path. Revisit if user demand emerges.
- **Attachment management** — multipart file upload/download, fundamentally different from JSON-only tool operations.
- **Board/Stack/Label CRUD** (create, update, delete) — current scope is card-centric operations. Board/stack/label structure is managed via the Nextcloud web UI.
- **ACL / sharing management** — permission management is an admin task, not an agent task.
- **Session management** — real-time liveness/sync for collaboration UI, not relevant for MCP tools.
- **Board import** — API v1.2 (unreleased), niche use case.

## Tech Stack

- **Languages**: Python 3.13+
- **Frameworks**: FastMCP (mcp-server), httpx, Pydantic, python-dotenv
- **Package manager**: uv
- **Testing**: pytest, pytest-asyncio, respx, pytest-cov
- **Linting/Typing**: ruff, pyright
- **Hosting/Cloud**: Local stdio; remote SSE planned
- **CI/CD**: GitHub Actions (lint → test → integration)
- **Layout**: Flat `mcp_deck_server/` package at repo root (not `src/`)
