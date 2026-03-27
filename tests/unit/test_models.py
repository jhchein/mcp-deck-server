from __future__ import annotations

from mcp_deck_server.models import Board, Card, Stack
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


def test_board_settings_list_is_accepted() -> None:
    """GET /boards returns settings as [] when details=false (decision 014)."""
    with_settings_list = load_fixture("board.json")
    with_settings_list["settings"] = []
    board = Board.model_validate(with_settings_list)
    assert board.settings == []
