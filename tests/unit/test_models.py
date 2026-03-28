from __future__ import annotations

from mcp_deck_server.models import Assignment, Board, Card, CardResult, Stack
from tests.helpers import load_fixture


def test_board_model_from_fixture() -> None:
    board = Board.model_validate(load_fixture("board.json"))
    assert board.id == 10
    assert board.title == "Board title"
    assert board.owner is not None
    assert board.owner.displayname == "Administrator"
    assert isinstance(board.settings, dict)


def test_stack_model_with_embedded_cards() -> None:
    stack = Stack.model_validate(load_fixture("stacks_list.json")[0])
    assert stack.cards is not None
    assert len(stack.cards) == 1
    assert stack.cards[0].id == 81


def test_card_model_from_fixture() -> None:
    card = Card.model_validate(load_fixture("card.json"))
    assert card.id == 81
    assert card.type == "plain"
    assert card.owner == "admin"


def test_card_model_with_assigned_users_fixture() -> None:
    card = Card.model_validate(load_fixture("assigned_card.json"))
    assert card.assignedUsers is not None
    assert len(card.assignedUsers) == 1
    assignment = card.assignedUsers[0]
    assert isinstance(assignment, Assignment)
    assert assignment.participant is not None
    assert assignment.participant.uid == "alice"


def test_card_model_done_is_datetime_string() -> None:
    card = Card.model_validate(load_fixture("card_done.json"))
    assert card.done == "2026-03-28T12:00:00+00:00"
    assert isinstance(card.done, str)


def test_card_result_model_wraps_context_and_card() -> None:
    card = Card.model_validate(load_fixture("assigned_card.json"))
    result = CardResult(
        board_id=10,
        board_title="Board title",
        stack_id=4,
        stack_title="ToDo",
        card=card,
    )
    assert result.board_id == 10
    assert result.stack_title == "ToDo"
    assert result.card.id == 81


def test_board_settings_list_is_accepted() -> None:
    """GET /boards returns settings as [] when details=false (decision 014)."""
    with_settings_list = load_fixture("board.json")
    with_settings_list["settings"] = []
    board = Board.model_validate(with_settings_list)
    assert board.settings == []
