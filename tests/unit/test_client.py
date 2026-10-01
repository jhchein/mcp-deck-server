from __future__ import annotations

import asyncio
import dataclasses

import httpx
import pytest
import respx

from mcp_deck_server import client as client_module
from mcp_deck_server.client import (
    DeckConnectionError,
    DeckHTTPError,
    DeckResponseError,
    make_nc_request,
)
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
async def test_make_nc_request_connection_error_redacts_request_details(
    test_client: httpx.AsyncClient, test_config
) -> None:
    def raise_connect_error(request: httpx.Request) -> None:
        raise httpx.ConnectError(
            "failed to connect to https://nextcloud.example.test/private",
            request=request,
        )

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards",
        ).mock(side_effect=raise_connect_error)

        with pytest.raises(DeckConnectionError) as error:
            await make_nc_request(test_client, test_config, "GET", "/boards")

    assert str(error.value) == "Deck API connection error"
    assert test_config.nc_url not in str(error.value)
    assert "/private" not in str(error.value)


@pytest.mark.asyncio
async def test_make_nc_request_malformed_json_raises_response_error(
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

        with pytest.raises(DeckResponseError):
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


@pytest.mark.asyncio
async def test_http_error_message_includes_deck_detail(
    test_client: httpx.AsyncClient, test_config
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="POST",
            url=f"{test_config.nc_url}/index.php/apps/deck/api/{test_config.nc_api_version}/boards/1/stacks/1/cards",
        ).mock(return_value=httpx.Response(400, json=load_fixture("error_400.json")))
        with pytest.raises(DeckHTTPError) as error:
            await make_nc_request(
                test_client,
                test_config,
                "POST",
                "/boards/1/stacks/1/cards",
                json={},
            )

    assert str(error.value) == "Deck API HTTP error 400: title must be provided"


def test_http_error_message_truncates_and_collapses_detail() -> None:
    body = '{"message": "' + ("word   " * 200) + '"}'

    message = str(DeckHTTPError(400, body))

    detail = message.removeprefix("Deck API HTTP error 400: ")
    assert len(detail) == client_module.MAX_ERROR_DETAIL_CHARS
    assert detail.endswith("…")
    assert "  " not in detail


@pytest.mark.parametrize(
    "body",
    ["<html><body>Bad gateway</body></html>", "[1, 2]", '{"message": 5}', '{"x": 1}'],
)
def test_http_error_message_ignores_unusable_bodies(body: str) -> None:
    assert str(DeckHTTPError(502, body)) == "Deck API HTTP error 502"


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []

    async def fake_sleep(delay: float) -> None:
        recorded.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)
    return recorded


def _boards_url(config) -> str:
    return f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}/boards"


@pytest.mark.asyncio
async def test_get_retries_transient_status_then_succeeds(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=2)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method="GET", url=_boards_url(config)).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(502),
                httpx.Response(200, json=[]),
            ]
        )
        response = await make_nc_request(test_client, config, "GET", "/boards")

    assert response == []
    assert route.call_count == 3
    assert sleeps == [0.5, 1.0]


@pytest.mark.asyncio
async def test_get_retry_honours_capped_retry_after(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=2)
    with respx.mock(assert_all_called=True) as router:
        router.route(method="GET", url=_boards_url(config)).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "2"}),
                httpx.Response(429, headers={"Retry-After": "3600"}),
                httpx.Response(200, json=[]),
            ]
        )
        await make_nc_request(test_client, config, "GET", "/boards")

    assert sleeps == [2.0, client_module.RETRY_MAX_DELAY_SECONDS]


@pytest.mark.asyncio
async def test_get_raises_after_retries_are_exhausted(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=1)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method="GET", url=_boards_url(config)).mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(DeckHTTPError) as error:
            await make_nc_request(test_client, config, "GET", "/boards")

    assert error.value.status_code == 503
    assert route.call_count == 2
    assert len(sleeps) == 1


@pytest.mark.asyncio
async def test_get_retries_transport_errors(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=2)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method="GET", url=_boards_url(config)).mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json=[])]
        )
        response = await make_nc_request(test_client, config, "GET", "/boards")

    assert response == []
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_get_raises_connection_error_when_transport_retries_exhausted(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=1)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method="GET", url=_boards_url(config)).mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with pytest.raises(DeckConnectionError):
            await make_nc_request(test_client, config, "GET", "/boards")

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_non_transport_request_errors_are_not_retried(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float]
) -> None:
    config = dataclasses.replace(test_config, max_retries=2)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method="GET", url=_boards_url(config)).mock(
            side_effect=httpx.TooManyRedirects("loop")
        )
        with pytest.raises(DeckConnectionError):
            await make_nc_request(test_client, config, "GET", "/boards")

    assert route.call_count == 1
    assert sleeps == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_writes_are_never_retried(
    test_client: httpx.AsyncClient, test_config, sleeps: list[float], method: str
) -> None:
    config = dataclasses.replace(test_config, max_retries=2)
    with respx.mock(assert_all_called=True) as router:
        route = router.route(method=method, url=_boards_url(config)).mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(DeckHTTPError):
            await make_nc_request(test_client, config, method, "/boards", json={})

    assert route.call_count == 1
    assert sleeps == []
