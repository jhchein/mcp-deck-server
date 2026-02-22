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

- _TBD_ (none specified yet)

## Tech Stack

- **Languages**: Python 3.13+
- **Frameworks**: FastMCP (mcp-server), httpx, Pydantic, python-dotenv
- **Package manager**: uv
- **Testing**: pytest, pytest-asyncio, respx, pytest-cov
- **Linting/Typing**: ruff, pyright
- **Hosting/Cloud**: Local stdio; remote SSE planned
- **CI/CD**: GitHub Actions (lint → test → integration)
- **Layout**: Flat `mcp_deck_server/` package at repo root (not `src/`)
