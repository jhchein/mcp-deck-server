from __future__ import annotations

import time

import httpx
import pytest
import respx

from mcp_deck_server import server
from mcp_deck_server.client import make_nc_request
from mcp_deck_server.server import DeckRuntime
from tests.helpers import load_fixture


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_make_nc_request_shared_vs_new_client_timing(test_config) -> None:
    iterations = 10

    with respx.mock(assert_all_called=False) as router:
        router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))

        shared_client = httpx.AsyncClient()
        try:
            shared_start = time.perf_counter()
            for _ in range(iterations):
                await make_nc_request(shared_client, test_config, "GET", "/boards")
            shared_elapsed = time.perf_counter() - shared_start
        finally:
            await shared_client.aclose()

        new_client_start = time.perf_counter()
        for _ in range(iterations):
            temp_client = httpx.AsyncClient()
            try:
                await make_nc_request(temp_client, test_config, "GET", "/boards")
            finally:
                await temp_client.aclose()
        new_client_elapsed = time.perf_counter() - new_client_start

    assert shared_elapsed > 0
    assert new_client_elapsed > 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_move_card_makes_two_api_calls(
    monkeypatch: pytest.MonkeyPatch,
    runtime: DeckRuntime,
) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)

    with respx.mock(assert_all_called=True) as router:
        stacks_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        reorder_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        card = await server.move_card(10, 81, "Done")

    assert card.id == 81
    assert stacks_route.call_count == 1
    assert reorder_route.call_count == 1
