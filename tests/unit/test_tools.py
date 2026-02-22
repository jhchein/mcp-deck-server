from __future__ import annotations

import httpx
import pytest
import respx

from mcp_deck_server.server import DeckRuntime
from mcp_deck_server import server
from tests.helpers import load_fixture


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.fixture
def patched_runtime(monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)


@pytest.mark.asyncio
async def test_list_boards(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))
        boards = await server.list_boards()

    assert len(boards) == 1
    assert boards[0].id == 10


@pytest.mark.asyncio
async def test_move_card_uses_embedded_cards_and_reorder(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        stacks_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        reorder_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card_reorder_response.json")))

        card = await server.move_card(10, 81, "Done")

    assert stacks_route.called
    assert reorder_route.called
    assert card.stackId == 5


@pytest.mark.asyncio
async def test_archive_card_uses_archive_endpoint(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/archive",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))
        card = await server.archive_card(10, 4, 81)

    assert route.called
    assert card.id == 81
