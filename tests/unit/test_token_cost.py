from __future__ import annotations

import json

import httpx
import pytest
import respx

from mcp_deck_server import server
from mcp_deck_server.server import DeckRuntime
from tests.helpers import load_fixture, text_payload


@pytest.fixture
def runtime(test_client: httpx.AsyncClient, test_config) -> DeckRuntime:
    return DeckRuntime(config=test_config, client=test_client)


@pytest.fixture(autouse=True)
def patched_runtime(monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)


def _stacks_with_cards(count: int) -> list[dict]:
    stacks = json.loads(json.dumps(load_fixture("stacks_list.json")))
    template = load_fixture("assigned_card.json")
    stacks[0]["cards"] = [{**template, "id": 1000 + n} for n in range(count)]
    return stacks


def _stacks_url(runtime: DeckRuntime, board_id: int) -> str:
    config = runtime.config
    return (
        f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}"
        f"/boards/{board_id}/stacks"
    )


@pytest.mark.asyncio
async def test_no_tool_advertises_an_output_schema() -> None:
    tools = await server.mcp.list_tools()

    assert tools
    assert [tool.name for tool in tools if tool.outputSchema is not None] == []


@pytest.mark.asyncio
async def test_results_are_json_text_without_structured_content(
    runtime: DeckRuntime,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(_stacks_url(runtime, 10)).mock(
            return_value=httpx.Response(200, json=_stacks_with_cards(2))
        )
        result = await server.mcp.call_tool("get_assigned_cards", {"board_ids": [10]})

    payload = text_payload(result)
    assert [item["card"]["id"] for item in payload["cards"]] == [1000, 1001]


@pytest.mark.asyncio
async def test_assigned_cards_are_capped_and_flagged(runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(_stacks_url(runtime, 10)).mock(
            return_value=httpx.Response(200, json=_stacks_with_cards(5))
        )
        result = await server.get_assigned_cards(board_ids=[10], limit=3)

    assert [item.card.id for item in result.cards] == [1000, 1001, 1002]
    assert result.total_matches == 5
    assert result.truncated is True


@pytest.mark.asyncio
async def test_assigned_cards_below_the_cap_are_not_truncated(
    runtime: DeckRuntime,
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(_stacks_url(runtime, 10)).mock(
            return_value=httpx.Response(200, json=_stacks_with_cards(2))
        )
        result = await server.get_assigned_cards(board_ids=[10])

    assert len(result.cards) == 2
    assert result.total_matches == 2
    assert result.truncated is False


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 1001])
async def test_assigned_cards_limit_is_bounded_by_the_schema(limit: int) -> None:
    with pytest.raises(Exception, match="limit"):
        await server.mcp.call_tool("get_assigned_cards", {"limit": limit})
