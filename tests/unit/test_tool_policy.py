from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Iterator

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from mcp_deck_server import server
from mcp_deck_server.client import DeckTimeoutError
from mcp_deck_server.server import DeckRuntime
from tests.unit.test_hardening import READ_TOOLS, WRITE_TOOLS


@pytest.fixture
def restore_tools() -> Iterator[None]:
    tools = server.mcp._tool_manager._tools
    saved = dict(tools)
    yield
    tools.clear()
    tools.update(saved)


@pytest.fixture
def deck_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("MCP_ENABLED_TOOLS", raising=False)
    return monkeypatch


@pytest.mark.asyncio
async def test_allowlist_keeps_only_listed_tools(
    deck_env: pytest.MonkeyPatch, restore_tools: None
) -> None:
    deck_env.setenv("MCP_ENABLED_TOOLS", "list_boards, get_card, move_card")

    async with server.deck_lifespan(server.mcp):
        names = {tool.name for tool in await server.mcp.list_tools()}

    assert names == {"list_boards", "get_card", "move_card"}


@pytest.mark.asyncio
async def test_read_only_wins_over_allowlisted_write_tool(
    deck_env: pytest.MonkeyPatch, restore_tools: None
) -> None:
    deck_env.setenv("MCP_READ_ONLY", "true")
    deck_env.setenv("MCP_ENABLED_TOOLS", "list_boards,create_card")

    async with server.deck_lifespan(server.mcp):
        names = {tool.name for tool in await server.mcp.list_tools()}

    assert names == {"list_boards"}


@pytest.mark.asyncio
async def test_unknown_tool_name_in_allowlist_fails_startup(
    deck_env: pytest.MonkeyPatch,
) -> None:
    deck_env.setenv("MCP_ENABLED_TOOLS", "list_boards,delete_everything")

    with pytest.raises(ValueError, match="delete_everything"):
        async with server.deck_lifespan(server.mcp):
            pass

    assert {tool.name for tool in await server.mcp.list_tools()} == (
        READ_TOOLS | WRITE_TOOLS
    )


@pytest.mark.asyncio
async def test_write_tool_outside_allowlist_is_refused(
    monkeypatch: pytest.MonkeyPatch, test_client: httpx.AsyncClient, test_config
) -> None:
    limited = DeckRuntime(
        config=dataclasses.replace(
            test_config, enabled_tools=frozenset({"archive_card"})
        ),
        client=test_client,
    )
    monkeypatch.setattr(server, "get_runtime", lambda: limited)

    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(ValueError, match="MCP_ENABLED_TOOLS"),
    ):
        await server.create_card(1, 2, "title")

    assert not router.calls


@pytest.mark.asyncio
async def test_tool_deadline_stops_slow_calls(
    monkeypatch: pytest.MonkeyPatch, test_client: httpx.AsyncClient, test_config
) -> None:
    quick = DeckRuntime(
        config=dataclasses.replace(test_config, tool_timeout=0.05),
        client=test_client,
    )
    monkeypatch.setattr(server, "get_runtime", lambda: quick)

    async def slow_response(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.route(method="GET").mock(side_effect=slow_response)
        with pytest.raises(ToolError, match=r"list_boards exceeded the 0\.05 s"):
            await server.mcp.call_tool("list_boards", {})


@pytest.mark.asyncio
async def test_tool_deadline_error_type(
    monkeypatch: pytest.MonkeyPatch, test_client: httpx.AsyncClient, test_config
) -> None:
    quick = DeckRuntime(
        config=dataclasses.replace(test_config, tool_timeout=0.05),
        client=test_client,
    )
    monkeypatch.setattr(server, "get_runtime", lambda: quick)
    tool = server.mcp._tool_manager.get_tool("list_boards")
    assert tool is not None

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.route(method="GET").mock(side_effect=slow)
        with pytest.raises(DeckTimeoutError):
            await tool.fn()


@pytest.mark.asyncio
async def test_inner_timeout_error_is_not_reported_as_deadline(
    monkeypatch: pytest.MonkeyPatch, test_client: httpx.AsyncClient, test_config
) -> None:
    runtime = DeckRuntime(config=test_config, client=test_client)
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)
    tool = server.mcp._tool_manager.get_tool("list_boards")
    assert tool is not None

    with respx.mock(assert_all_called=False) as router:
        router.route(method="GET").mock(side_effect=TimeoutError("boom"))
        with pytest.raises(TimeoutError, match="boom"):
            await tool.fn()
