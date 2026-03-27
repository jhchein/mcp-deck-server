from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

from mcp_deck_server.config import DeckConfig
from mcp_deck_server.server import DeckRuntime


def _get_required_env(var_name: str) -> str:
    value = os.getenv(var_name, "").strip()
    if not value:
        pytest.skip(f"{var_name} is required for integration tests")
    return value


@pytest.fixture
def test_board_id() -> int:
    board_id_raw = os.getenv("DECK_TEST_BOARD_ID", "").strip()
    if not board_id_raw:
        pytest.skip("DECK_TEST_BOARD_ID is required for integration tests")
    try:
        return int(board_id_raw)
    except ValueError:
        pytest.skip("DECK_TEST_BOARD_ID must be an integer")


@pytest.fixture
async def live_runtime() -> AsyncIterator[DeckRuntime]:
    config = DeckConfig(
        nc_url=_get_required_env("NC_URL").rstrip("/"),
        nc_user=_get_required_env("NC_USER"),
        nc_app_password=_get_required_env("NC_APP_PASSWORD"),
        nc_api_version=os.getenv("NC_API_VERSION", "v1.1").strip() or "v1.1",
        transport="stdio",
        request_timeout=float(
            os.getenv("MCP_REQUEST_TIMEOUT", "30.0").strip() or "30.0"
        ),
    )

    client = httpx.AsyncClient(
        timeout=config.request_timeout,
        auth=(config.nc_user, config.nc_app_password),
        headers={
            "OCS-APIRequest": "true",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        yield DeckRuntime(config=config, client=client)
    finally:
        await client.aclose()
