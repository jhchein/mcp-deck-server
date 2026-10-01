from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys
from pathlib import Path

import anyio
import httpx
import pytest
import respx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_deck_server import client as client_module
from mcp_deck_server import server
from mcp_deck_server.server import DeckRuntime
from tests.unit.test_hardening import READ_TOOLS, WRITE_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.fixture
def patched_runtime(monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)


def _boards_url(runtime: DeckRuntime) -> str:
    config = runtime.config
    return f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}/boards"


@pytest.mark.asyncio
@pytest.mark.usefixtures("patched_runtime")
async def test_tool_call_logs_name_outcome_and_duration_only(
    runtime: DeckRuntime, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="mcp_deck_server.server")
    with respx.mock() as router:
        router.get(_boards_url(runtime)).mock(
            return_value=httpx.Response(200, json=[{"id": 1, "title": "Private"}])
        )
        await server.mcp.call_tool("list_boards", {})

    lines = [r.getMessage() for r in caplog.records if "tool=" in r.getMessage()]
    assert len(lines) == 1
    assert lines[0].startswith("tool=list_boards outcome=ok duration_ms=")
    assert "Private" not in caplog.text
    assert runtime.config.nc_app_password not in caplog.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("patched_runtime")
async def test_failed_tool_call_logs_the_error_class(
    runtime: DeckRuntime, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="mcp_deck_server.server")
    with respx.mock() as router:
        router.get(_boards_url(runtime)).mock(return_value=httpx.Response(401))
        with pytest.raises(Exception, match="401"):
            await server.mcp.call_tool("list_boards", {})

    assert "tool=list_boards outcome=error:DeckHTTPError" in caplog.text


@pytest.mark.asyncio
async def test_deadline_is_logged_as_timeout(
    monkeypatch: pytest.MonkeyPatch,
    test_client: httpx.AsyncClient,
    test_config,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quick = DeckRuntime(
        config=dataclasses.replace(test_config, tool_timeout=0.05),
        client=test_client,
    )
    monkeypatch.setattr(server, "get_runtime", lambda: quick)
    caplog.set_level(logging.INFO, logger="mcp_deck_server.server")

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as router:
        router.get(_boards_url(quick)).mock(side_effect=slow)
        with pytest.raises(Exception, match="deadline"):
            await server.mcp.call_tool("list_boards", {})

    assert "tool=list_boards outcome=timeout" in caplog.text


@pytest.mark.asyncio
async def test_retries_are_logged_without_host_or_credentials(
    test_client: httpx.AsyncClient,
    test_config,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", no_sleep)
    config = dataclasses.replace(test_config, max_retries=1)
    caplog.set_level(logging.WARNING, logger="mcp_deck_server.client")
    url = f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}/boards"
    with respx.mock() as router:
        router.get(url).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
        )
        await client_module.make_nc_request(test_client, config, "GET", "/boards")

    assert "deck_retry method=GET path=/index.php/apps/deck/api/v1.1/boards" in (
        caplog.text
    )
    assert "reason=HTTP 503" in caplog.text
    assert "nextcloud.example.test" not in caplog.text


async def _advertised_tools(**env: str) -> set[str]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_deck_server"],
        cwd=REPO_ROOT,
        env={
            "NC_URL": "https://nextcloud.example.test",
            "NC_USER": "alice",
            "NC_APP_PASSWORD": "secret",
            "MCP_READ_ONLY": "false",
            "MCP_ENABLED_TOOLS": "",
            "PYTHONPATH": str(REPO_ROOT),
            **env,
        },
    )
    with anyio.fail_after(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return {tool.name for tool in (await session.list_tools()).tools}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, READ_TOOLS | WRITE_TOOLS),
        ({"MCP_READ_ONLY": "true"}, READ_TOOLS),
        (
            {"MCP_ENABLED_TOOLS": "list_boards,create_card"},
            {"list_boards", "create_card"},
        ),
    ],
    ids=["default", "read-only", "allowlist"],
)
async def test_stdio_server_advertises_the_configured_tools(
    env: dict[str, str], expected: set[str]
) -> None:
    assert await _advertised_tools(**env) == expected
