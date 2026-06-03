from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from mcp_deck_server import server
from mcp_deck_server.client import DeckAPIError
from mcp_deck_server.server import DeckRuntime

logging.getLogger("httpx").setLevel(logging.WARNING)


async def _measure(
    label: str,
    call: Callable[[], Awaitable[Any]],
) -> tuple[str, float, Any]:
    start = time.perf_counter()
    result = await call()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return label, elapsed_ms, result


def _configured_test_board_id() -> int | None:
    raw_value = os.getenv("DECK_TEST_BOARD_ID", "").strip()
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        pytest.skip("DECK_TEST_BOARD_ID must be an integer")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_live_read_performance_is_measured_without_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    live_runtime: DeckRuntime,
) -> None:
    monkeypatch.setattr(server, "get_runtime", lambda: live_runtime)
    timings: list[tuple[str, float]] = []

    label, elapsed_ms, boards = await _measure("list_boards", server.list_boards)
    timings.append((label, elapsed_ms))
    assert boards

    configured_board_id = _configured_test_board_id()
    if configured_board_id is None:
        board_id = boards[0].id
        board_selection = "first_accessible"
    else:
        board_id = configured_board_id
        board_selection = "configured_test_board"
        assert any(board.id == board_id for board in boards)
    assert board_id is not None

    label, elapsed_ms, board = await _measure(
        "get_board",
        lambda: server.get_board(board_id),
    )
    timings.append((label, elapsed_ms))
    assert board.id == board_id

    label, elapsed_ms, stacks = await _measure(
        "list_stacks",
        lambda: server.list_stacks(board_id),
    )
    timings.append((label, elapsed_ms))
    assert stacks

    first_stack_id = stacks[0].id
    if first_stack_id is not None:
        label, elapsed_ms, cards = await _measure(
            "list_cards_first_stack",
            lambda: server.list_cards(board_id, first_stack_id),
        )
        timings.append((label, elapsed_ms))
        assert isinstance(cards, list)

    label, elapsed_ms, scoped_assigned_cards = await _measure(
        "get_assigned_cards_scoped",
        lambda: server.get_assigned_cards(board_ids=[board_id]),
    )
    timings.append((label, elapsed_ms))
    assert isinstance(scoped_assigned_cards, list)

    label, elapsed_ms, unscoped_assigned_cards = await _measure(
        "get_assigned_cards_unscoped",
        server.get_assigned_cards,
    )
    timings.append((label, elapsed_ms))
    assert isinstance(unscoped_assigned_cards, list)

    concurrent_start = time.perf_counter()
    await asyncio.gather(server.list_boards(), server.list_stacks(board_id))
    concurrent_elapsed_ms = (time.perf_counter() - concurrent_start) * 1000
    timings.append(("concurrent_list_boards_and_stacks", concurrent_elapsed_ms))

    card_count = sum(len(stack.cards or []) for stack in stacks)
    print("\nPERF live read summary:")
    print(
        "  "
        f"api_version={live_runtime.config.nc_api_version} "
        f"board_selection={board_selection} "
        f"board_count={len(boards)} "
        f"stack_count={len(stacks)} "
        f"card_count={card_count}"
    )
    for timing_label, timing_ms in timings:
        print(f"  {timing_label}_ms={timing_ms:.2f}")

    assert all(timing_ms > 0 for _, timing_ms in timings)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_live_move_card_performance_uses_disposable_test_card(
    monkeypatch: pytest.MonkeyPatch,
    live_runtime: DeckRuntime,
) -> None:
    board_id = _configured_test_board_id()
    if board_id is None:
        pytest.skip("DECK_TEST_BOARD_ID is required for live mutation performance")

    monkeypatch.setattr(server, "get_runtime", lambda: live_runtime)
    timings: list[tuple[str, float]] = []
    card_id: int | None = None
    cleanup_stack_id: int | None = None

    _, elapsed_ms, stacks = await _measure(
        "list_stacks_for_move",
        lambda: server.list_stacks(board_id),
    )
    timings.append(("list_stacks_for_move", elapsed_ms))

    if len(stacks) < 2:
        pytest.skip("At least two stacks are required for live move_card performance")

    source_stack = stacks[0]
    target_stack = stacks[1]
    if source_stack.id is None or target_stack.id is None or not target_stack.title:
        pytest.skip(
            "Source and target stacks must have IDs and the target needs a title"
        )

    cleanup_stack_id = source_stack.id
    try:
        label, elapsed_ms, created_card = await _measure(
            "create_card_for_move",
            lambda: server.create_card(
                board_id,
                source_stack.id,
                f"phase-5-performance-test-{int(time.time())}",
                "created by live performance measurement",
            ),
        )
        timings.append((label, elapsed_ms))
        card_id = created_card.id
        assert card_id is not None

        label, elapsed_ms, moved_card = await _measure(
            "move_card",
            lambda: server.move_card(board_id, card_id, target_stack.title or ""),
        )
        timings.append((label, elapsed_ms))
        assert moved_card.id == card_id
        cleanup_stack_id = moved_card.stackId or target_stack.id
    finally:
        if card_id is not None and cleanup_stack_id is not None:
            try:
                label, elapsed_ms, _ = await _measure(
                    "archive_card_cleanup",
                    lambda: server.archive_card(board_id, cleanup_stack_id, card_id),
                )
                timings.append((label, elapsed_ms))
            except DeckAPIError as error:
                pytest.fail(f"Live performance cleanup failed: {error!r}")

    print("\nPERF live mutation summary:")
    print("  board_selection=configured_test_board write_scope=disposable_card")
    for timing_label, timing_ms in timings:
        print(f"  {timing_label}_ms={timing_ms:.2f}")

    assert all(timing_ms > 0 for _, timing_ms in timings)
