from __future__ import annotations

from typing import Any

import pytest

from mcp_deck_server.models import Card, Owner
from mcp_deck_server.server import _mutation_result, _resolve_owner


def _card(owner: Owner | str | None) -> Card:
    return Card(id=1, title="t", owner=owner)


@pytest.mark.parametrize(
    ("explicit", "current", "expected"),
    [
        ({"uid": "bob"}, _card(Owner(uid="alice")), {"uid": "bob"}),
        (None, _card(Owner(uid="alice")), {"uid": "alice"}),
        (None, _card("alice"), "alice"),
        (None, _card(None), "fallback-user"),
    ],
    ids=["explicit", "owner-object", "owner-string", "no-owner"],
)
def test_resolve_owner_prefers_explicit_then_current_then_fallback(
    explicit: dict[str, Any] | None, current: Card, expected: Any
) -> None:
    assert _resolve_owner(explicit, current, "fallback-user") == expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (None, {"success": True}),
        ({"id": 3}, {"id": 3}),
        ([1, 2], {"success": True, "raw": [1, 2]}),
    ],
)
def test_mutation_result_normalises_empty_and_non_dict_bodies(
    result: Any, expected: dict[str, Any]
) -> None:
    assert _mutation_result(result) == expected
