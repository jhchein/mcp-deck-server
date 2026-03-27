from __future__ import annotations

import pytest

from mcp_deck_server import server
from mcp_deck_server.server import DeckRuntime


@pytest.mark.integration
@pytest.mark.asyncio
async def test_card_roundtrip_on_configured_board(
    monkeypatch: pytest.MonkeyPatch,
    live_runtime: DeckRuntime,
    test_board_id: int,
) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: live_runtime)

    boards = await server.list_boards()
    assert any(board.id == test_board_id for board in boards)

    stacks = await server.list_stacks(test_board_id)
    assert stacks

    source_stack_id = stacks[0].id
    assert source_stack_id is not None

    created_card = await server.create_card(
        test_board_id,
        source_stack_id,
        "integration-roundtrip",
        "created by integration test",
    )
    assert created_card.id is not None

    fetched_card = await server.get_card(
        test_board_id, source_stack_id, created_card.id
    )
    assert fetched_card.id == created_card.id

    updated_card = await server.update_card(
        test_board_id,
        source_stack_id,
        created_card.id,
        title="integration-roundtrip-updated",
        description="updated by integration test",
    )
    assert updated_card.id == created_card.id

    if len(stacks) > 1 and stacks[1].title:
        moved_card = await server.move_card(
            test_board_id, created_card.id, stacks[1].title
        )
        assert moved_card.id == created_card.id

    await server.archive_card(test_board_id, source_stack_id, created_card.id)
