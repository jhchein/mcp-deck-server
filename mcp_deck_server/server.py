from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .client import make_nc_request
from .config import DeckConfig, load_config
from .models import Board, Card, CardResult, Owner, Stack


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


def _resolve_text_field(value: str | None, current: str | None) -> str:
    if value is None:
        return current or ""
    return value


def _resolve_datetime_field(value: str | None, current: str | None) -> str | None:
    if value is None:
        return current
    if value == "":
        return None
    return value


def get_runtime() -> DeckRuntime:
    context = mcp.get_context()
    runtime = context.request_context.lifespan_context
    if not isinstance(runtime, DeckRuntime):
        raise ValueError("Lifespan context is unavailable")
    return runtime


def _card_is_assigned_to_user(card: Card, user_id: str) -> bool:
    for assignment in card.assignedUsers or []:
        participant = assignment.participant
        if participant is not None and participant.uid == user_id:
            return True
    return False


def _card_matches_done_filter(card: Card, done: bool | None) -> bool:
    if done is None:
        return True
    # Card.done is an ISO-8601 datetime string or None, not a boolean.
    return (card.done is not None) is done


@mcp.tool()
async def list_boards() -> list[Board]:
    """List all boards the authenticated user can access.

    Returns board metadata including IDs and labels. Use this to discover board
    IDs before calling board-specific tools.
    """
    runtime = get_runtime()
    response = await make_nc_request(runtime.client, runtime.config, "GET", "/boards")
    return [Board.model_validate(board) for board in response]


@mcp.tool()
async def get_board(board_id: int) -> Board:
    """Get full details for a single board, including labels and ACL data.

    Use this to look up label IDs before calling assign_label_to_card.
    """
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
    """List all stacks on a board.

    Returns stack IDs, titles, and order. Prefer get_assigned_cards if you need
    cards for a specific user across boards.
    """
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
    """List all cards in a specific stack.

    Returns cards with titles, labels, assignees, and status. Prefer
    get_assigned_cards to find a user's cards across boards.
    """
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
async def get_assigned_cards(
    user_id: Annotated[
        str | None,
        Field(
            description=(
                "Nextcloud user ID. Defaults to the authenticated user if omitted."
            )
        ),
    ] = None,
    board_ids: Annotated[
        list[int] | None,
        Field(
            description=(
                "Restrict search to these board IDs. Omit to search all "
                "accessible boards."
            )
        ),
    ] = None,
    done: Annotated[
        bool | None,
        Field(
            description=(
                "Filter: True=only done cards, False=only open cards, " "None=all."
            )
        ),
    ] = None,
) -> list[CardResult]:
    """Find cards assigned to a user across boards.

    Filters by user, board, and done status, and returns board and stack context
    with each card. Prefer this over list_stacks plus manual filtering.
    """
    runtime = get_runtime()
    resolved_user_id = user_id or runtime.config.nc_user

    if board_ids:
        boards_to_query = [(board_id, "") for board_id in board_ids]
    else:
        boards_response = await make_nc_request(
            runtime.client,
            runtime.config,
            "GET",
            "/boards",
        )
        boards = [Board.model_validate(board_data) for board_data in boards_response]
        boards_to_query = [
            (board.id, board.title or "") for board in boards if board.id is not None
        ]

    results: list[CardResult] = []
    for board_id, board_title in boards_to_query:
        stacks_response = await make_nc_request(
            runtime.client,
            runtime.config,
            "GET",
            f"/boards/{board_id}/stacks",
        )
        stacks = [Stack.model_validate(stack_data) for stack_data in stacks_response]
        for stack in stacks:
            if stack.id is None:
                continue
            for card in stack.cards or []:
                if not _card_is_assigned_to_user(card, resolved_user_id):
                    continue
                if not _card_matches_done_filter(card, done):
                    continue
                results.append(
                    CardResult(
                        board_id=board_id,
                        board_title=board_title,
                        stack_id=stack.id,
                        stack_title=stack.title or "",
                        card=card,
                    )
                )
    return results


@mcp.tool()
async def create_card(
    board_id: int,
    stack_id: int,
    title: str,
    description: Annotated[
        str,
        Field(description="Card description. Defaults to empty."),
    ] = "",
) -> Card:
    """Create a new card in a stack.

    Returns the created card.
    """
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
    """Get full details for a single card.

    Returns the card with description, labels, assignees, and status fields.
    """
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
    title: Annotated[
        str | None,
        Field(description="New title. None to keep current."),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New description text, '' to clear, None to keep current."),
    ] = None,
    duedate: Annotated[
        str | None,
        Field(
            description=("ISO-8601 datetime string, '' to clear, None to keep current.")
        ),
    ] = None,
    done: Annotated[
        str | None,
        Field(
            description=(
                "ISO-8601 datetime string to mark done, '' to clear, None to keep "
                "current. Never send a boolean."
            )
        ),
    ] = None,
    card_type: str | None = None,
    owner: dict[str, Any] | None = None,
    order: Annotated[
        int | None,
        Field(description="Sort position within the stack. None to keep current."),
    ] = None,
) -> Card:
    """Update card fields without resetting omitted values.

    The current card is fetched first and only provided fields are changed. For
    text fields, None keeps the current value and an empty string clears it.
    For duedate and done, use None to keep, an empty string to clear, or an
    ISO-8601 datetime string to set a new value.
    """
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

    resolved_description = _resolve_text_field(description, current_card.description)
    resolved_duedate = _resolve_datetime_field(duedate, current_card.duedate)
    resolved_done = _resolve_datetime_field(done, current_card.done)

    payload: dict[str, Any] = {
        "title": title,
        "description": resolved_description,
        "type": card_type if card_type is not None else (current_card.type or "plain"),
        "order": order if order is not None else (current_card.order or 0),
        "duedate": resolved_duedate,
        "done": resolved_done,
    }

    # If owner is omitted, preserve current owner from the fetched card.
    if owner_payload is not None:
        payload["owner"] = owner_payload
    else:
        payload["owner"] = runtime.config.nc_user

    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}",
        json=payload,
    )
    return Card.model_validate(response)


@mcp.tool()
async def move_card(
    board_id: int,
    card_id: int,
    target_stack_name: Annotated[
        str,
        Field(description="Name of the destination stack. Case-insensitive."),
    ],
) -> Card:
    """Move a card to a different stack on the same board.

    Stack name matching is case-insensitive. If no stack matches, the error
    lists the available stack names.
    """
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
    """Archive a card.

    Archived cards are removed from the active board view.
    """
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
    """Remove a label from a card."""
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
    label_id: Annotated[
        int,
        Field(description="Label ID from the board's labels list (see get_board)."),
    ],
) -> dict[str, Any]:
    """Add a label to a card.

    Get available label IDs from get_board first.
    """
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
    user_id: Annotated[
        str,
        Field(description="Nextcloud user ID of the user to assign."),
    ],
) -> dict[str, Any]:
    """Assign a user to a card by Nextcloud user ID."""
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
    """Remove a user assignment from a card."""
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
