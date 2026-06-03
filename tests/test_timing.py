from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import respx

from mcp_deck_server import server
from mcp_deck_server.client import DeckConnectionError, make_nc_request
from mcp_deck_server.models import Stack
from mcp_deck_server.server import DeckRuntime
from tests.helpers import load_fixture


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


def _large_stacks_payload(stack_count: int, cards_per_stack: int) -> list[dict]:
    card_template = load_fixture("card.json")
    stacks: list[dict] = []

    for stack_index in range(stack_count):
        stack_id = stack_index + 1
        stack = {
            "id": stack_id,
            "title": f"Stack {stack_id}",
            "boardId": 10,
            "order": stack_index,
            "deletedAt": 0,
            "lastModified": 1541426139 + stack_index,
            "cards": [],
        }
        for card_index in range(cards_per_stack):
            card = dict(card_template)
            card["id"] = (stack_id * 1000) + card_index
            card["stackId"] = stack_id
            card["order"] = card_index
            stack["cards"].append(card)
        stacks.append(stack)

    return stacks


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

    print(
        "\nPERF mocked connection reuse: "
        f"iterations={iterations} "
        f"shared_ms={shared_elapsed * 1000:.2f} "
        f"new_client_ms={new_client_elapsed * 1000:.2f}"
    )
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
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/5/cards/81/reorder",
        ).mock(
            return_value=httpx.Response(
                200, json=load_fixture("card_reorder_response.json")
            )
        )

        move_start = time.perf_counter()
        card = await server.move_card(10, 81, "Done")
        move_elapsed = time.perf_counter() - move_start

    print(
        "\nPERF mocked move_card: "
        f"api_calls={stacks_route.call_count + reorder_route.call_count} "
        f"elapsed_ms={move_elapsed * 1000:.2f}"
    )
    assert card.id == 81
    assert stacks_route.call_count == 1
    assert reorder_route.call_count == 1


@pytest.mark.slow
def test_pydantic_model_validate_large_payload_timing() -> None:
    stack_count = 5
    cards_per_stack = 25
    iterations = 50
    payload = _large_stacks_payload(stack_count, cards_per_stack)
    payload_bytes = len(json.dumps(payload).encode("utf-8"))

    parse_start = time.perf_counter()
    parsed_stacks: list[Stack] = []
    for _ in range(iterations):
        parsed_stacks = [Stack.model_validate(stack_data) for stack_data in payload]
    parse_elapsed = time.perf_counter() - parse_start

    print(
        "\nPERF mocked pydantic: "
        f"stacks={stack_count} "
        f"cards={stack_count * cards_per_stack} "
        f"payload_bytes={payload_bytes} "
        f"iterations={iterations} "
        f"total_ms={parse_elapsed * 1000:.2f} "
        f"per_iteration_ms={(parse_elapsed * 1000) / iterations:.2f}"
    )
    assert len(parsed_stacks) == stack_count
    assert sum(len(stack.cards or []) for stack in parsed_stacks) == (
        stack_count * cards_per_stack
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_timeout_surfaces_as_connection_error_promptly(test_config) -> None:
    url = (
        f"{test_config.nc_url}/index.php/apps/deck/api/"
        f"{test_config.nc_api_version}/boards"
    )
    request = httpx.Request("GET", url)

    async with httpx.AsyncClient() as client:
        with respx.mock(assert_all_called=True) as router:
            router.route(method="GET", url=url).mock(
                side_effect=httpx.ReadTimeout("timed out", request=request)
            )

            timeout_start = time.perf_counter()
            with pytest.raises(DeckConnectionError):
                await make_nc_request(client, test_config, "GET", "/boards")
            timeout_elapsed = time.perf_counter() - timeout_start

    print(f"\nPERF mocked timeout path: elapsed_ms={timeout_elapsed * 1000:.2f}")
    assert timeout_elapsed < 1.0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_shared_client_handles_concurrent_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
    runtime: DeckRuntime,
) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)

    with respx.mock(assert_all_called=False) as router:
        boards_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards",
        ).mock(return_value=httpx.Response(200, json=load_fixture("boards_list.json")))
        stacks_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        concurrent_start = time.perf_counter()
        results = await asyncio.gather(
            *[
                server.list_boards() if call_index % 2 == 0 else server.list_stacks(10)
                for call_index in range(10)
            ]
        )
        concurrent_elapsed = time.perf_counter() - concurrent_start

    print(
        "\nPERF mocked concurrency: "
        f"calls={len(results)} "
        f"elapsed_ms={concurrent_elapsed * 1000:.2f}"
    )
    assert len(results) == 10
    assert boards_route.call_count == 5
    assert stacks_route.call_count == 5
