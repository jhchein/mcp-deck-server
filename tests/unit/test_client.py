from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from mcp_deck_server.client import DeckConnectionError, DeckHTTPError, make_nc_request
from tests.helpers import load_fixture


@pytest.mark.asyncio
async def test_make_nc_request_success_json(
    test_client: httpx.AsyncClient, test_config
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))
        response = await make_nc_request(test_client, test_config, "GET", "/boards")

    assert route.called
    assert isinstance(response, list)
    assert response[0]["id"] == 10


@pytest.mark.asyncio
async def test_make_nc_request_204(test_client: httpx.AsyncClient, test_config) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="PUT",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards/1/stacks/1/cards/1/removeLabel",
        ).mock(return_value=httpx.Response(204))
        response = await make_nc_request(
            test_client,
            test_config,
            "PUT",
            "/boards/1/stacks/1/cards/1/removeLabel",
            json={"labelId": 1},
        )

    assert response is None


@pytest.mark.asyncio
async def test_make_nc_request_http_error(
    test_client: httpx.AsyncClient, test_config
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards/999",
        ).mock(return_value=httpx.Response(404, json=load_fixture("error_404.json")))
        with pytest.raises(DeckHTTPError) as error:
            await make_nc_request(test_client, test_config, "GET", "/boards/999")

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_make_nc_request_connection_error(
    test_client: httpx.AsyncClient, test_config
) -> None:
    def raise_timeout(_: httpx.Request) -> None:
        raise httpx.ReadTimeout("timed out")

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(side_effect=raise_timeout)
        with pytest.raises(DeckConnectionError):
            await make_nc_request(test_client, test_config, "GET", "/boards")


@pytest.mark.asyncio
async def test_make_nc_request_malformed_json_raises_value_error(
    test_client: httpx.AsyncClient, test_config
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(
            return_value=httpx.Response(
                200,
                text="not-json",
                headers={"Content-Type": "application/json"},
            )
        )

        with pytest.raises(ValueError):
            await make_nc_request(test_client, test_config, "GET", "/boards")


@pytest.mark.asyncio
async def test_make_nc_request_large_payload_parses(
    test_client: httpx.AsyncClient, test_config
) -> None:
    large_payload = [
        {
            "id": index,
            "title": f"Board {index}",
            "archived": False,
        }
        for index in range(1000)
    ]

    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=large_payload))

        response = await make_nc_request(test_client, test_config, "GET", "/boards")

    assert route.called
    assert isinstance(response, list)
    assert len(response) == 1000


@pytest.mark.asyncio
async def test_make_nc_request_concurrent_calls_complete(
    test_client: httpx.AsyncClient, test_config
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))

        results = await asyncio.gather(
            *[
                make_nc_request(test_client, test_config, "GET", "/boards")
                for _ in range(5)
            ]
        )

    assert route.call_count == 5
    assert len(results) == 5
    assert all(isinstance(result, list) for result in results)
