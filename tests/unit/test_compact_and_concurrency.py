from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from mcp_deck_server import server
from mcp_deck_server.client import DeckHTTPError
from mcp_deck_server.models import Card, CardSummary
from mcp_deck_server.server import DeckRuntime
from tests.helpers import load_fixture, text_payload


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.fixture
def patched_runtime(monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)


def _api(runtime: DeckRuntime, path: str) -> str:
    return (
        f"{runtime.config.nc_url}/index.php/apps/deck/api/"
        f"{runtime.config.nc_api_version}{path}"
    )


def _assigned_stacks() -> list[dict]:
    stacks = json.loads(json.dumps(load_fixture("stacks_list.json")))
    stacks[0]["cards"] = [load_fixture("assigned_card.json")]
    return stacks


@pytest.mark.asyncio
async def test_get_assigned_cards_fetches_boards_concurrently_within_the_cap(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    board_count = 12
    in_flight = 0
    peak = 0

    async def slow_stacks(_: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return httpx.Response(200, json=_assigned_stacks())

    with respx.mock(assert_all_called=True) as router:
        for board_id in range(1, board_count + 1):
            router.route(
                method="GET", url=_api(runtime, f"/boards/{board_id}/stacks")
            ).mock(side_effect=slow_stacks)

        result = await server.get_assigned_cards(
            board_ids=list(range(1, board_count + 1))
        )

    assert 1 < peak <= server.MAX_CONCURRENT_BOARD_REQUESTS
    assert [item.board_id for item in result.cards] == list(range(1, board_count + 1))


@pytest.mark.asyncio
async def test_get_assigned_cards_keeps_board_order_when_completion_order_differs(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=_assigned_stacks())

    with respx.mock(assert_all_called=True) as router:
        router.route(method="GET", url=_api(runtime, "/boards/1/stacks")).mock(
            side_effect=slow
        )
        router.route(method="GET", url=_api(runtime, "/boards/2/stacks")).mock(
            return_value=httpx.Response(403, json={"message": "no"})
        )
        router.route(method="GET", url=_api(runtime, "/boards/3/stacks")).mock(
            return_value=httpx.Response(200, json=_assigned_stacks())
        )

        result = await server.get_assigned_cards(board_ids=[1, 2, 3])

    assert [item.board_id for item in result.cards] == [1, 3]
    assert [item.board_id for item in result.skipped_boards] == [2]


@pytest.mark.asyncio
async def test_get_assigned_cards_fails_fast_on_unexpected_error(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.route(method="GET", url=_api(runtime, "/boards/1/stacks")).mock(
            return_value=httpx.Response(500, json={"message": "boom"})
        )
        router.route(method="GET", url=_api(runtime, "/boards/2/stacks")).mock(
            return_value=httpx.Response(200, json=_assigned_stacks())
        )

        with pytest.raises(DeckHTTPError, match="boom"):
            await server.get_assigned_cards(board_ids=[1, 2])


@pytest.mark.asyncio
async def test_list_cards_compact_returns_summaries(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    stacks = _assigned_stacks()
    stacks[0]["cards"][0]["labels"] = [{"id": 1, "title": "urgent"}]

    with respx.mock(assert_all_called=True) as router:
        router.route(method="GET", url=_api(runtime, "/boards/10/stacks")).mock(
            return_value=httpx.Response(200, json=stacks)
        )
        cards = await server.list_cards(10, 4, compact=True)

    assert len(cards) == 1
    summary = cards[0]
    assert isinstance(summary, CardSummary)
    assert summary.labels == ["urgent"]
    assert summary.assignees == ["alice"]
    assert summary.stackId == 4


@pytest.mark.asyncio
async def test_list_cards_defaults_to_full_cards(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(method="GET", url=_api(runtime, "/boards/10/stacks")).mock(
            return_value=httpx.Response(200, json=_assigned_stacks())
        )
        cards = await server.list_cards(10, 4)

    assert isinstance(cards[0], Card)


@pytest.mark.asyncio
async def test_get_assigned_cards_compact_returns_summaries(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(method="GET", url=_api(runtime, "/boards/10/stacks")).mock(
            return_value=httpx.Response(200, json=_assigned_stacks())
        )
        result = await server.get_assigned_cards(board_ids=[10], compact=True)

    assert isinstance(result.cards[0].card, CardSummary)


@pytest.mark.asyncio
async def test_compact_payload_is_smaller_over_the_mcp_boundary(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    """The tool result serialises as a summary, not as a coerced full card."""
    with respx.mock(assert_all_called=False) as router:
        router.route(method="GET", url=_api(runtime, "/boards/10/stacks")).mock(
            return_value=httpx.Response(200, json=_assigned_stacks())
        )
        full_content = await server.mcp.call_tool(
            "get_assigned_cards", {"board_ids": [10], "compact": False}
        )
        compact_content = await server.mcp.call_tool(
            "get_assigned_cards", {"board_ids": [10], "compact": True}
        )
    full = text_payload(full_content)
    compact = text_payload(compact_content)

    full_card = full["cards"][0]["card"]
    compact_card = compact["cards"][0]["card"]
    assert "owner" in full_card
    assert "description" not in compact_card
    assert set(compact_card) == set(CardSummary.model_fields)
    assert len(json.dumps(compact)) < len(json.dumps(full))
