from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from .client import make_nc_request
from .config import DeckConfig, load_config
from .models import Board, Card, Owner, Stack


@dataclass(frozen=True)
class DeckRuntime:
    config: DeckConfig
    client: httpx.AsyncClient


@asynccontextmanager
async def deck_lifespan(_: FastMCP):
    config = load_config()
    client = httpx.AsyncClient(
        timeout=config.request_timeout,
        auth=(config.nc_user, config.nc_app_password),
        headers={
            "OCS-APIRequest": "true",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        yield DeckRuntime(config=config, client=client)
    finally:
        await client.aclose()


mcp = FastMCP("deck", lifespan=deck_lifespan)


def get_runtime() -> DeckRuntime:
    context = mcp.get_context()
    runtime = context.request_context.lifespan_context
    if not isinstance(runtime, DeckRuntime):
        raise ValueError("Lifespan context is unavailable")
    return runtime


@mcp.tool()
async def list_boards() -> list[Board]:
    runtime = get_runtime()
    response = await make_nc_request(runtime.client, runtime.config, "GET", "/boards")
    return [Board.model_validate(board) for board in response]


@mcp.tool()
async def get_board(board_id: int) -> Board:
    runtime = get_runtime()
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}",
    )
    return Board.model_validate(response)


@mcp.tool()
async def list_stacks(board_id: int) -> list[Stack]:
    runtime = get_runtime()
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks",
    )
    return [Stack.model_validate(stack) for stack in response]


@mcp.tool()
async def list_cards(board_id: int, stack_id: int) -> list[Card]:
    """List cards in a stack. Extracts cards from the stacks endpoint
    (no dedicated list-cards endpoint exists in the Deck API)."""
    runtime = get_runtime()
    stacks_data = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks",
    )
    for stack_data in stacks_data:
        stack = Stack.model_validate(stack_data)
        if stack.id == stack_id:
            return stack.cards or []
    raise ValueError(f"Stack {stack_id} not found on board {board_id}")


@mcp.tool()
async def create_card(
    board_id: int,
    stack_id: int,
    title: str,
    description: str = "",
) -> Card:
    runtime = get_runtime()
    payload = {
        "title": title,
        "description": description,
        "type": "plain",
    }
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "POST",
        f"/boards/{board_id}/stacks/{stack_id}/cards",
        json=payload,
    )
    return Card.model_validate(response)


@mcp.tool()
async def get_card(board_id: int, stack_id: int, card_id: int) -> Card:
    runtime = get_runtime()
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
    )
    return Card.model_validate(response)


@mcp.tool()
async def update_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    title: str | None = None,
    description: str | None = None,
    duedate: str | None = None,
    card_type: str = "plain",
    owner: dict | None = None,
) -> Card:
    runtime = get_runtime()
    current_card_data = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
    )
    current_card = Card.model_validate(current_card_data)

    if title is None:
        title = current_card.title

    owner_payload = owner
    if owner_payload is None:
        if isinstance(current_card.owner, Owner):
            owner_payload = current_card.owner.model_dump(exclude_none=True)
        else:
            owner_payload = current_card.owner

    payload: dict[str, Any] = {
        "title": title,
        "type": card_type,
    }

    # `None` means "leave unchanged". Empty string explicitly clears string fields.
    if description is not None:
        payload["description"] = description
    if duedate is not None:
        payload["duedate"] = duedate

    # If owner is omitted, preserve current owner from the fetched card.
    if owner_payload is not None:
        payload["owner"] = owner_payload

    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
        json=payload,
    )
    return Card.model_validate(response)


@mcp.tool()
async def move_card(board_id: int, card_id: int, target_stack_name: str) -> Card:
    runtime = get_runtime()
    stacks_data = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks",
    )
    stacks = [Stack.model_validate(stack_data) for stack_data in stacks_data]

    target_stack_id: int | None = None
    current_stack_id: int | None = None
    current_card_order: int | None = None

    for stack in stacks:
        if (
            stack.title
            and stack.title.lower() == target_stack_name.lower()
            and stack.id is not None
        ):
            target_stack_id = stack.id

        for card in stack.cards or []:
            if card.archived:
                continue
            if card.id == card_id and stack.id is not None:
                current_stack_id = stack.id
                current_card_order = card.order

    if target_stack_id is None:
        available_stacks = ", ".join(stack.title or "<untitled>" for stack in stacks)
        error_message = (
            f"Stack '{target_stack_name}' not found. "
            f"Available stacks: {available_stacks}"
        )
        raise ValueError(error_message)

    if current_stack_id is None:
        raise ValueError(f"Card with ID {card_id} not found on board {board_id}")

    payload = {"stackId": target_stack_id, "order": current_card_order or 999}
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{current_stack_id}/cards/{card_id}/reorder",
        json=payload,
    )
    if isinstance(response, list):
        if not response:
            raise ValueError("Empty list response from card reorder endpoint")
        # The reorder endpoint returns all affected cards; find ours by ID.
        for item in response:
            validated = Card.model_validate(item)
            if validated.id == card_id:
                return validated
        # Card not in response list — fetch it directly.
        refreshed = await make_nc_request(
            runtime.client,
            runtime.config,
            "GET",
            f"/boards/{board_id}/stacks/{target_stack_id}/cards/{card_id}",
        )
        return Card.model_validate(refreshed)
    return Card.model_validate(response)


@mcp.tool()
async def archive_card(board_id: int, stack_id: int, card_id: int) -> Card:
    runtime = get_runtime()
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/archive",
    )
    return Card.model_validate(response)


@mcp.tool()
async def remove_label_from_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    label_id: int,
) -> dict[str, Any]:
    runtime = get_runtime()
    payload = {"labelId": label_id}
    result = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/removeLabel",
        json=payload,
    )
    if result is None:
        return {"success": True}
    if not isinstance(result, dict):
        return {"success": True, "raw": result}
    return result


@mcp.tool()
async def assign_label_to_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    label_id: int,
) -> dict[str, Any]:
    runtime = get_runtime()
    payload = {"labelId": label_id}
    result = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/assignLabel",
        json=payload,
    )
    if result is None:
        return {"success": True}
    if not isinstance(result, dict):
        return {"success": True, "raw": result}
    return result


@mcp.tool()
async def assign_user_to_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    user_id: str,
) -> dict[str, Any]:
    runtime = get_runtime()
    payload = {"userId": user_id}
    result = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/assignUser",
        json=payload,
    )
    if result is None:
        return {"success": True}
    if not isinstance(result, dict):
        return {"success": True, "raw": result}
    return result


@mcp.tool()
async def unassign_user_from_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    user_id: str,
) -> dict[str, Any]:
    runtime = get_runtime()
    payload = {"userId": user_id}
    result = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/unassignUser",
        json=payload,
    )
    if result is None:
        return {"success": True}
    if not isinstance(result, dict):
        return {"success": True, "raw": result}
    return result
