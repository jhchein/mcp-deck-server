from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from mcp_deck_server import server
from mcp_deck_server.server import DeckRuntime
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
async def test_get_board(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10",
        ).mock(return_value=httpx.Response(200, json=load_fixture("board.json")))
        board = await server.get_board(10)

    assert route.called
    assert board.id == 10


@pytest.mark.asyncio
async def test_list_stacks(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))
        stacks = await server.list_stacks(10)

    assert route.called
    assert len(stacks) == 2
    assert stacks[0].id == 4


@pytest.mark.asyncio
async def test_list_cards(patched_runtime: None, runtime: DeckRuntime) -> None:
    """list_cards extracts cards from stacks endpoint (decision 014)."""
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))
        cards = await server.list_cards(10, 4)

    assert route.called
    assert len(cards) == 1
    assert cards[0].id == 81


@pytest.mark.asyncio
async def test_list_cards_stack_not_found(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        with pytest.raises(ValueError, match="Stack 999 not found"):
            await server.list_cards(10, 999)


@pytest.mark.asyncio
async def test_get_assigned_cards_defaults_to_self_across_accessible_boards(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    first_board_stacks = json.loads(json.dumps(load_fixture("stacks_list.json")))
    first_board_stacks[0]["cards"] = [load_fixture("assigned_card.json")]

    second_board_stacks = json.loads(json.dumps(load_fixture("stacks_list.json")))
    second_board_stacks[0]["cards"] = []
    second_board_stacks[1]["cards"] = [load_fixture("assigned_card.json")]
    second_board_stacks[1]["cards"][0]["id"] = 82
    second_board_stacks[1]["cards"][0]["stackId"] = 5
    second_board_stacks[1]["cards"][0]["title"] = "Second board task"

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards",
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    *load_fixture("boards_list.json"),
                    {"id": 11, "title": "Board two"},
                ],
            )
        )
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=first_board_stacks))
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/11/stacks",
        ).mock(return_value=httpx.Response(200, json=second_board_stacks))

        cards = await server.get_assigned_cards()

    assert len(cards) == 2
    assert cards[0].board_id == 10
    assert cards[0].card.assignedUsers is not None
    assert cards[0].card.assignedUsers[0].participant is not None
    assert cards[0].card.assignedUsers[0].participant.uid == runtime.config.nc_user
    assert cards[1].board_id == 11


@pytest.mark.asyncio
async def test_get_assigned_cards_uses_explicit_board_ids_without_listing_boards(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    stacks_payload = json.loads(json.dumps(load_fixture("stacks_list.json")))
    stacks_payload[0]["cards"] = [load_fixture("assigned_card.json")]

    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        cards = await server.get_assigned_cards(board_ids=[10])

    assert route.called
    assert len(cards) == 1
    assert cards[0].board_id == 10
    assert cards[0].board_title == ""


@pytest.mark.asyncio
async def test_get_assigned_cards_filters_by_explicit_user_and_done(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    matching_card = load_fixture("assigned_card.json")
    done_card = json.loads(json.dumps(matching_card))
    done_card["id"] = 82
    done_card["title"] = "Done card"
    done_card["done"] = "2026-03-28T12:00:00+00:00"

    other_user_card = json.loads(json.dumps(matching_card))
    other_user_card["id"] = 83
    other_user_card["assignedUsers"][0]["participant"]["uid"] = "bob"

    stacks_payload = json.loads(json.dumps(load_fixture("stacks_list.json")))
    stacks_payload[0]["cards"] = [matching_card, done_card, other_user_card]

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        cards = await server.get_assigned_cards(
            user_id="alice",
            board_ids=[10],
            done=True,
        )

    assert len(cards) == 1
    assert cards[0].card.id == 82


@pytest.mark.asyncio
async def test_get_assigned_cards_returns_empty_when_no_matching_assignment(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    unmatched_card = json.loads(json.dumps(load_fixture("assigned_card.json")))
    unmatched_card["assignedUsers"][0]["participant"]["uid"] = "bob"
    stacks_payload = json.loads(json.dumps(load_fixture("stacks_list.json")))
    stacks_payload[0]["cards"] = [unmatched_card]

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        cards = await server.get_assigned_cards(board_ids=[10])

    assert cards == []


@pytest.mark.asyncio
async def test_create_card(patched_runtime: None, runtime: DeckRuntime) -> None:
    captured_payload: dict[str, object] = {}

    def capture_create(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="POST",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards",
        ).mock(side_effect=capture_create)
        card = await server.create_card(10, 4, "New Card", "Notes")

    assert route.called
    assert captured_payload == {
        "title": "New Card",
        "description": "Notes",
        "type": "plain",
    }
    assert card.id == 81


@pytest.mark.asyncio
async def test_get_card(patched_runtime: None, runtime: DeckRuntime) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))
        card = await server.get_card(10, 4, 81)

    assert route.called
    assert card.id == 81


@pytest.mark.asyncio
async def test_move_card_uses_embedded_cards_and_reorder(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        stacks_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        reorder_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(
            return_value=httpx.Response(
                200, json=load_fixture("card_reorder_response.json")
            )
        )

        card = await server.move_card(10, 81, "Done")

    assert stacks_route.called
    assert reorder_route.called
    assert card.stackId == 5


@pytest.mark.asyncio
async def test_move_card_stack_not_found_raises_value_error(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        with pytest.raises(ValueError, match="Stack 'Missing' not found"):
            await server.move_card(10, 81, "Missing")

    assert route.called


@pytest.mark.asyncio
async def test_move_card_card_not_found_raises_value_error(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    stacks_payload = json.loads(json.dumps(load_fixture("stacks_list.json")))
    for stack in stacks_payload:
        stack["cards"] = []

    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        with pytest.raises(ValueError, match="Card with ID 81 not found"):
            await server.move_card(10, 81, "Done")

    assert route.called


@pytest.mark.asyncio
async def test_move_card_empty_list_reorder_response_raises_value_error(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=[]))

        with pytest.raises(ValueError, match="Empty list response"):
            await server.move_card(10, 81, "Done")

    assert route.called


@pytest.mark.asyncio
async def test_move_card_ignores_archived_matching_card(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    stacks_payload = json.loads(json.dumps(load_fixture("stacks_list.json")))
    stacks_payload[0]["cards"] = [
        {
            "id": 81,
            "title": "Archived Card",
            "stackId": 4,
            "type": "plain",
            "owner": "admin",
            "order": 1,
            "archived": True,
        }
    ]

    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        with pytest.raises(ValueError, match="Card with ID 81 not found"):
            await server.move_card(10, 81, "Done")

    assert route.called


@pytest.mark.asyncio
async def test_move_card_finds_correct_card_in_reorder_list(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    """Reorder returns all affected cards; move_card must find ours by ID."""
    other_card = {"id": 999, "title": "Other", "stackId": 5, "type": "plain"}
    our_card = load_fixture("card.json")  # id=81
    reorder_payload = [other_card, our_card]

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=reorder_payload))

        card = await server.move_card(10, 81, "Done")

    assert card.id == 81


@pytest.mark.asyncio
async def test_move_card_fetches_card_when_not_in_reorder_list(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    """If the moved card is missing from the reorder response, fetch it directly."""
    other_card = {"id": 999, "title": "Other", "stackId": 5, "type": "plain"}
    reorder_payload = [other_card]

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=reorder_payload))

        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/5/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        card = await server.move_card(10, 81, "Done")

    assert card.id == 81


@pytest.mark.asyncio
async def test_archive_card_uses_archive_endpoint(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/archive",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))
        card = await server.archive_card(10, 4, 81)

    assert route.called
    assert card.id == 81


@pytest.mark.asyncio
async def test_update_card_omitted_fields_are_preserved(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        get_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        put_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        card = await server.update_card(10, 4, 81)

    assert get_route.called
    assert put_route.called
    assert captured_payload["title"] == "Test"
    assert captured_payload["description"] == ""
    assert captured_payload["duedate"] == "2019-12-24T19:29:30+00:00"
    assert captured_payload["done"] is None
    assert captured_payload["order"] == 999
    assert captured_payload["type"] == "plain"
    assert captured_payload["owner"] == "admin"
    assert card.id == 81


@pytest.mark.asyncio
async def test_update_card_with_overrides(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(
            10,
            4,
            81,
            title="Renamed",
            description="Edited",
            duedate="2026-03-01T00:00:00+00:00",
            done="2026-03-02T00:00:00+00:00",
            card_type="plain",
            owner={"uid": "alice"},
            order=123,
        )

    assert route.called
    assert captured_payload["title"] == "Renamed"
    assert captured_payload["description"] == "Edited"
    assert captured_payload["duedate"] == "2026-03-01T00:00:00+00:00"
    assert captured_payload["done"] == "2026-03-02T00:00:00+00:00"
    assert captured_payload["owner"] == {"uid": "alice"}
    assert captured_payload["type"] == "plain"
    assert captured_payload["order"] == 123


@pytest.mark.asyncio
async def test_update_card_empty_strings_clear_text_fields(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        get_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        put_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(10, 4, 81, description="", duedate="", done="")

    assert get_route.called
    assert put_route.called
    assert captured_payload["description"] == ""
    assert captured_payload["duedate"] is None
    assert captured_payload["done"] is None


@pytest.mark.asyncio
async def test_update_card_preserves_existing_card_type_and_order(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}
    card_payload = load_fixture("card.json")
    card_payload["type"] = "checklist"
    card_payload["order"] = 42

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=card_payload)

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=card_payload))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(10, 4, 81)

    assert captured_payload["type"] == "checklist"
    assert captured_payload["order"] == 42


@pytest.mark.asyncio
async def test_update_card_preserves_done_datetime_when_omitted(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}
    card_payload = load_fixture("card_done.json")

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=card_payload)

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=card_payload))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(10, 4, 81)

    assert captured_payload["done"] == "2026-03-28T12:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("done", "true"),
        ("done", "2026-04-02"),
        ("done", "2026-04-02T12:00:00"),
        ("duedate", "not-a-date"),
    ],
)
async def test_update_card_rejects_non_timestamp_datetime_fields(
    patched_runtime: None,
    runtime: DeckRuntime,
    field_name: str,
    field_value: str,
) -> None:
    with respx.mock(assert_all_called=False) as router:
        get_route = router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        put_route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        with pytest.raises(
            ValueError,
            match=r"Datetime fields must be ISO-8601 timestamps like '2026-04-02T00:00:00\+00:00'; use '' to clear or None to keep current\.",
        ):
            await server.update_card(10, 4, 81, **{field_name: field_value})

    assert get_route.called
    assert not put_route.called


@pytest.mark.asyncio
async def test_remove_label_from_card_with_no_content_returns_success(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/removeLabel",
        ).mock(return_value=httpx.Response(204))
        result = await server.remove_label_from_card(10, 4, 81, 7)

    assert route.called
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_remove_label_from_card_with_raw_response_wraps_result(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/removeLabel",
        ).mock(return_value=httpx.Response(200, json=["ok"]))
        result = await server.remove_label_from_card(10, 4, 81, 7)

    assert route.called
    assert result == {"success": True, "raw": ["ok"]}


@pytest.mark.asyncio
async def test_assign_label_to_card_with_dict_response(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignLabel",
        ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = await server.assign_label_to_card(10, 4, 81, 7)

    assert route.called
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_assign_label_to_card_with_no_content_returns_success(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignLabel",
        ).mock(return_value=httpx.Response(204))
        result = await server.assign_label_to_card(10, 4, 81, 7)

    assert route.called
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_assign_label_to_card_with_raw_response_wraps_result(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignLabel",
        ).mock(return_value=httpx.Response(200, json=["ok"]))
        result = await server.assign_label_to_card(10, 4, 81, 7)

    assert route.called
    assert result == {"success": True, "raw": ["ok"]}


@pytest.mark.asyncio
async def test_get_runtime_invalid_lifespan_context_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_context = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context={})
    )
    monkeypatch.setattr(server.mcp, "get_context", lambda: invalid_context)

    with pytest.raises(ValueError, match="Lifespan context is unavailable"):
        server.get_runtime()


def test_get_runtime_returns_deck_runtime(
    monkeypatch: pytest.MonkeyPatch, runtime: DeckRuntime
) -> None:
    valid_context = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=runtime)
    )
    monkeypatch.setattr(server.mcp, "get_context", lambda: valid_context)

    resolved_runtime = server.get_runtime()

    assert resolved_runtime is runtime


@pytest.mark.asyncio
async def test_deck_lifespan_creates_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, test_config
) -> None:
    monkeypatch.setattr(server, "load_config", lambda: test_config)

    runtime_obj: DeckRuntime | None = None
    async with server.deck_lifespan(server.mcp) as lifespan_runtime:
        runtime_obj = lifespan_runtime
        assert isinstance(runtime_obj, DeckRuntime)
        assert runtime_obj.config == test_config
        assert not runtime_obj.client.is_closed

    assert runtime_obj is not None
    assert runtime_obj.client.is_closed


@pytest.mark.asyncio
async def test_update_card_preserves_owner_from_owner_object(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}
    card_payload = load_fixture("card.json")
    card_payload["owner"] = {
        "uid": "admin",
        "displayname": "Administrator",
    }

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=card_payload))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(10, 4, 81)

    assert captured_payload["owner"] == {
        "uid": "admin",
        "displayname": "Administrator",
    }
    assert captured_payload["description"] == ""
    assert captured_payload["done"] is None
    assert captured_payload["order"] == 999


@pytest.mark.asyncio
async def test_move_card_non_list_reorder_response_returns_card(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=load_fixture("stacks_list.json")))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/reorder",
        ).mock(return_value=httpx.Response(200, json=load_fixture("card.json")))

        card = await server.move_card(10, 81, "Done")

    assert card.id == 81


@pytest.mark.asyncio
async def test_remove_label_from_card_with_dict_response(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/removeLabel",
        ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = await server.remove_label_from_card(10, 4, 81, 7)

    assert route.called
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_assign_user_to_card_with_dict_response(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignUser",
        ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = await server.assign_user_to_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_assign_user_to_card_with_no_content_returns_success(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignUser",
        ).mock(return_value=httpx.Response(204))
        result = await server.assign_user_to_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_assign_user_to_card_with_raw_response_wraps_result(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/assignUser",
        ).mock(return_value=httpx.Response(200, json=["ok"]))
        result = await server.assign_user_to_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"success": True, "raw": ["ok"]}


@pytest.mark.asyncio
async def test_unassign_user_from_card_with_dict_response(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/unassignUser",
        ).mock(return_value=httpx.Response(200, json={"status": "ok"}))
        result = await server.unassign_user_from_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_unassign_user_from_card_with_no_content_returns_success(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/unassignUser",
        ).mock(return_value=httpx.Response(204))
        result = await server.unassign_user_from_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_unassign_user_from_card_with_raw_response_wraps_result(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81/unassignUser",
        ).mock(return_value=httpx.Response(200, json=["ok"]))
        result = await server.unassign_user_from_card(10, 4, 81, "alice")

    assert route.called
    assert result == {"success": True, "raw": ["ok"]}


@pytest.mark.asyncio
async def test_get_assigned_cards_skips_stack_with_null_id(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    stacks_payload = [
        {
            "id": None,
            "title": "Ghost",
            "boardId": 10,
            "order": 0,
            "cards": [
                load_fixture("assigned_card.json"),
            ],
        },
        {
            "id": 5,
            "title": "Real",
            "boardId": 10,
            "order": 1,
            "cards": [
                load_fixture("assigned_card.json"),
            ],
        },
    ]

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks",
        ).mock(return_value=httpx.Response(200, json=stacks_payload))

        cards = await server.get_assigned_cards(board_ids=[10])

    assert len(cards) == 1
    assert cards[0].stack_id == 5


@pytest.mark.asyncio
async def test_update_card_falls_back_to_config_user_when_owner_is_null(
    patched_runtime: None, runtime: DeckRuntime
) -> None:
    captured_payload: dict[str, object] = {}
    card_payload = json.loads(json.dumps(load_fixture("card.json")))
    card_payload["owner"] = None

    def capture_update(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=load_fixture("card.json"))

    with respx.mock(assert_all_called=True) as router:
        router.route(
            method="GET",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(return_value=httpx.Response(200, json=card_payload))

        router.route(
            method="PUT",
            url=f"{runtime.config.nc_url}/index.php/apps/deck/api/{runtime.config.nc_api_version}/boards/10/stacks/4/cards/81",
        ).mock(side_effect=capture_update)

        await server.update_card(10, 4, 81)

    assert captured_payload["owner"] == "alice"
