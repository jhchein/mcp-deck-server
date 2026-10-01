from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from mcp_deck_server import server
from mcp_deck_server.server import DeckRuntime
from tests.helpers import load_fixture

WRITE_TOOLS = {
    "create_card",
    "update_card",
    "move_card",
    "archive_card",
    "assign_label_to_card",
    "remove_label_from_card",
    "assign_user_to_card",
    "unassign_user_from_card",
}
READ_TOOLS = {
    "list_boards",
    "get_board",
    "list_stacks",
    "list_cards",
    "get_assigned_cards",
    "get_card",
}


@pytest.fixture
def restore_tools() -> Iterator[None]:
    """Undo tool removal done by read-only lifespan tests."""
    tools = server.mcp._tool_manager._tools
    saved = dict(tools)
    yield
    tools.clear()
    tools.update(saved)


@pytest.fixture
def read_only_runtime(
    monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime
) -> DeckRuntime:
    read_only = DeckRuntime(
        config=dataclasses.replace(runtime.config, read_only=True),
        client=runtime.client,
    )
    monkeypatch.setattr(server, "get_runtime", lambda: read_only)
    return read_only


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.mark.asyncio
async def test_every_tool_declares_annotations() -> None:
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    assert set(tools) == WRITE_TOOLS | READ_TOOLS
    for name, tool in tools.items():
        assert tool.annotations is not None, name
        assert tool.annotations.readOnlyHint is (name in READ_TOOLS), name


@pytest.mark.asyncio
async def test_destructive_and_idempotent_hints_match_behaviour() -> None:
    tools = {tool.name: tool.annotations for tool in await server.mcp.list_tools()}

    assert tools["create_card"] is not None
    assert tools["create_card"].idempotentHint is False
    assert tools["create_card"].destructiveHint is False
    for name in ("update_card", "remove_label_from_card", "unassign_user_from_card"):
        assert tools[name] is not None
        assert tools[name].destructiveHint is True, name


@pytest.mark.asyncio
async def test_read_only_lifespan_removes_write_tools(
    monkeypatch: pytest.MonkeyPatch, restore_tools: None
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_READ_ONLY", "true")

    async with server.deck_lifespan(server.mcp) as lifespan_runtime:
        assert lifespan_runtime.config.read_only is True
        names = {tool.name for tool in await server.mcp.list_tools()}

    assert names == READ_TOOLS


@pytest.mark.asyncio
async def test_read_only_lifespan_is_repeatable(
    monkeypatch: pytest.MonkeyPatch, restore_tools: None
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_READ_ONLY", "true")

    async with server.deck_lifespan(server.mcp):
        pass
    async with server.deck_lifespan(server.mcp):
        names = {tool.name for tool in await server.mcp.list_tools()}

    assert names == READ_TOOLS


@pytest.mark.asyncio
async def test_default_lifespan_keeps_write_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)

    async with server.deck_lifespan(server.mcp):
        names = {tool.name for tool in await server.mcp.list_tools()}

    assert names == WRITE_TOOLS | READ_TOOLS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda: server.create_card(1, 2, "title"),
        lambda: server.update_card(1, 2, 3, title="title"),
        lambda: server.move_card(1, 3, "Done"),
        lambda: server.archive_card(1, 2, 3),
        lambda: server.assign_label_to_card(1, 2, 3, 4),
        lambda: server.remove_label_from_card(1, 2, 3, 4),
        lambda: server.assign_user_to_card(1, 2, 3, "bob"),
        lambda: server.unassign_user_from_card(1, 2, 3, "bob"),
    ],
)
async def test_write_tools_refuse_in_read_only_mode(
    read_only_runtime: DeckRuntime, call
) -> None:
    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(ValueError, match="MCP_READ_ONLY"),
    ):
        await call()

    assert router.calls.call_count == 0


@pytest.mark.asyncio
async def test_read_tools_still_work_in_read_only_mode(
    read_only_runtime: DeckRuntime,
) -> None:
    config = read_only_runtime.config
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))

        boards = await server.list_boards()

    assert boards[0].id == 10


@pytest.mark.asyncio
async def test_writes_emit_audit_line_without_content(
    monkeypatch: pytest.MonkeyPatch,
    runtime: DeckRuntime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)
    config = runtime.config

    with (
        caplog.at_level(logging.INFO, logger=server.audit_logger.name),
        respx.mock(assert_all_called=True) as router,
    ):
        router.route(
            method="POST",
            url=f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}/boards/10/stacks/4/cards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        await server.create_card(10, 4, "Visible title", "secret description")

    assert "write tool=create_card board_id=10 stack_id=4" in caplog.text
    assert "secret description" not in caplog.text
    assert "Visible title" not in caplog.text
    assert config.nc_app_password not in caplog.text


@pytest.mark.asyncio
async def test_title_and_description_schemas_declare_length_caps() -> None:
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    create_props = tools["create_card"].inputSchema["properties"]
    assert create_props["title"]["maxLength"] == server.MAX_TITLE_LENGTH
    assert create_props["description"]["maxLength"] == server.MAX_DESCRIPTION_LENGTH
    update_props = tools["update_card"].inputSchema["properties"]
    assert update_props["title"]["anyOf"][0]["maxLength"] == server.MAX_TITLE_LENGTH


@pytest.mark.asyncio
async def test_overlong_title_is_rejected_before_any_request() -> None:
    with pytest.raises(ToolError):
        await server.mcp.call_tool(
            "create_card",
            {
                "board_id": 1,
                "stack_id": 1,
                "title": "x" * (server.MAX_TITLE_LENGTH + 1),
            },
        )
