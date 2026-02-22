from __future__ import annotations

import httpx
import pytest

from mcp_deck_server.config import DeckConfig
from mcp_deck_server.models import Board, Card, Stack
from tests.helpers import load_fixture



@pytest.fixture
def test_config() -> DeckConfig:
    return DeckConfig(
        nc_url="https://nextcloud.example.test",
        nc_user="alice",
        nc_app_password="app-password",
        nc_api_version="v1.1",
        transport="stdio",
        request_timeout=30.0,
    )


@pytest.fixture
def test_client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


@pytest.fixture
def make_board() -> Board:
    data = load_fixture("board.json")
    return Board.model_validate(data)


@pytest.fixture
def make_stack() -> Stack:
    data = load_fixture("stack.json")
    return Stack.model_validate(data)


@pytest.fixture
def make_card() -> Card:
    data = load_fixture("card.json")
    return Card.model_validate(data)
