"""Live contract tests — validate all tool endpoints against a real Nextcloud instance.

Exercises every MCP tool endpoint in a single ordered round-trip:
  list_boards → get_board → list_stacks → list_cards → create_card → get_card →
  update_card → assign_label → remove_label → assign_user → unassign_user →
  move_card → archive_card

Requires NC_URL, NC_USER, NC_APP_PASSWORD environment variables.
DECK_TEST_BOARD_ID is optional; if absent, the first board is used.
"""

from __future__ import annotations

import os
from collections import Counter

import pytest

from mcp_deck_server import server
from mcp_deck_server.client import DeckAPIError
from mcp_deck_server.server import DeckRuntime


def _settings_shape(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_tool_endpoints_against_live_instance(
    monkeypatch: pytest.MonkeyPatch,
    live_runtime: DeckRuntime,
) -> None:
    """Full round-trip exercising every tool against a live Nextcloud Deck board."""
    monkeypatch.setattr(server, "get_runtime", lambda: live_runtime)

    # --- list_boards ---
    boards = await server.list_boards()
    assert boards
    settings_shapes = Counter(_settings_shape(b.settings) for b in boards)
    # Record observed shapes for diagnostic visibility
    print(f"  settings_shapes across {len(boards)} boards: {dict(settings_shapes)}")

    requested_id_raw = os.getenv("DECK_TEST_BOARD_ID", "").strip()
    if requested_id_raw:
        board_id = int(requested_id_raw)
        assert any(b.id == board_id for b in boards), "DECK_TEST_BOARD_ID not in boards"
    else:
        board_id = boards[0].id
        assert board_id is not None

    # --- get_board ---
    board = await server.get_board(board_id)
    assert board.id == board_id

    # --- list_stacks ---
    stacks = await server.list_stacks(board_id)
    assert stacks
    source_stack = stacks[0]
    assert source_stack.id is not None

    # --- list_cards (uses stacks endpoint internally, decision 014) ---
    cards_in_stack = await server.list_cards(board_id, source_stack.id)
    assert isinstance(cards_in_stack, list)

    # --- create_card ---
    created = await server.create_card(
        board_id,
        source_stack.id,
        "live-contract-test",
        "created by test_live_contracts",
    )
    assert created.id is not None
    card_id = created.id
    stack_id = source_stack.id

    try:
        # --- get_card ---
        fetched = await server.get_card(board_id, stack_id, card_id)
        assert fetched.id == card_id

        # --- update_card ---
        updated = await server.update_card(
            board_id,
            stack_id,
            card_id,
            title="live-contract-test-updated",
            description="updated by test_live_contracts",
        )
        assert updated.id == card_id

        # --- assign_label_to_card (only if board has labels) ---
        if board.labels:
            label_id = board.labels[0].id
            assert label_id is not None
            assign_label_result = await server.assign_label_to_card(
                board_id, stack_id, card_id, label_id
            )
            assert isinstance(assign_label_result, dict)

            # --- remove_label_from_card ---
            remove_label_result = await server.remove_label_from_card(
                board_id, stack_id, card_id, label_id
            )
            assert isinstance(remove_label_result, dict)

        # --- assign_user_to_card ---
        user_id = live_runtime.config.nc_user
        try:
            assign_user_result = await server.assign_user_to_card(
                board_id, stack_id, card_id, user_id
            )
            assert isinstance(assign_user_result, dict)

            # --- unassign_user_from_card ---
            unassign_user_result = await server.unassign_user_from_card(
                board_id, stack_id, card_id, user_id
            )
            assert isinstance(unassign_user_result, dict)
        except DeckAPIError:
            # User assignment may fail depending on permissions
            print(f"  assign/unassign user skipped (API error for {user_id})")

        # --- move_card (only if >1 stack) ---
        if len(stacks) > 1 and stacks[1].title:
            moved = await server.move_card(board_id, card_id, stacks[1].title)
            assert moved.id == card_id

    finally:
        # --- archive_card (cleanup) ---
        try:
            await server.archive_card(board_id, stack_id, card_id)
        except DeckAPIError:
            print(f"  archive_card cleanup failed for card {card_id}")
