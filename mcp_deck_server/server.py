from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import DeckHTTPError, DeckTimeoutError, make_nc_request
from .config import DeckConfig, load_config
from .models import (
    AssignedCards,
    Board,
    Card,
    CardResult,
    CardSummary,
    Owner,
    SkippedBoard,
    Stack,
)

# Boards the user cannot read or that no longer exist should not abort a
# cross-board search.
_SKIPPABLE_BOARD_STATUS_CODES = frozenset({403, 404})

# Deck limits card titles to 255 characters. The description cap is a sanity
# limit against runaway agent payloads, not a Deck-enforced value.
MAX_TITLE_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 100_000

# Default cap on cards returned by get_assigned_cards; protects agent context.
DEFAULT_ASSIGNED_CARDS_LIMIT = 200
MAX_ASSIGNED_CARDS_LIMIT = 1000

# Upper bound on simultaneous Deck requests during a cross-board search.
MAX_CONCURRENT_BOARD_REQUESTS = 5

# A dead host should fail fast instead of consuming the whole request timeout.
CONNECT_TIMEOUT_SECONDS = 10.0

_COMPACT_DESCRIPTION = (
    "Return slim card summaries (id, title, stackId, duedate, done, archived, "
    "label titles, assignee user IDs) instead of full cards. Use get_card for "
    "the description and other details."
)


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger(f"{__name__}.audit")

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_CREATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False
)
_ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True
)
_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True
)

_TOOL_NAMES: set[str] = set()
_WRITE_TOOL_NAMES: set[str] = set()


@dataclass(frozen=True)
class DeckRuntime:
    config: DeckConfig
    client: httpx.AsyncClient


def create_http_client(config: DeckConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            config.request_timeout,
            connect=min(CONNECT_TIMEOUT_SECONDS, config.request_timeout),
        ),
        auth=(config.nc_user, config.nc_app_password),
        headers={
            "OCS-APIRequest": "true",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )


@asynccontextmanager
async def deck_lifespan(app: FastMCP):
    config = load_config()
    _apply_tool_policy(app, config)
    client = create_http_client(config)
    try:
        yield DeckRuntime(config=config, client=client)
    finally:
        await client.aclose()


mcp = FastMCP("deck", lifespan=deck_lifespan)


def _instrument(function: Callable[..., Awaitable[Any]]) -> Any:
    """Bound a tool call by MCP_TOOL_TIMEOUT and log how it went.

    The per-request timeout alone allows a multi-board search to run for
    minutes when Deck is slow; the agent would rather get a clear error. The
    log line carries the tool name, outcome and duration only, never arguments
    or results.
    """

    @functools.wraps(function)
    async def run(*args: Any, **kwargs: Any) -> Any:
        timeout = get_runtime().config.tool_timeout
        deadline = asyncio.timeout(timeout)
        started = time.perf_counter()
        outcome = "ok"
        try:
            async with deadline:
                return await function(*args, **kwargs)
        except TimeoutError as error:
            if not deadline.expired():
                outcome = "error:TimeoutError"
                raise
            outcome = "timeout"
            raise DeckTimeoutError(
                f"{function.__name__} exceeded the {timeout:g} s tool deadline "
                "(MCP_TOOL_TIMEOUT)"
            ) from error
        except BaseException as error:
            outcome = f"error:{type(error).__name__}"
            raise
        finally:
            logger.info(
                "tool=%s outcome=%s duration_ms=%.0f",
                function.__name__,
                outcome,
                (time.perf_counter() - started) * 1000,
            )

    return run


def _register_tool[F: Callable[..., Any]](
    function: F, annotations: ToolAnnotations, *, writes: bool
) -> F:
    _TOOL_NAMES.add(function.__name__)
    if writes:
        _WRITE_TOOL_NAMES.add(function.__name__)
    # Without structured output FastMCP omits the outputSchema and the duplicate
    # structuredContent; clients still receive the JSON text content.
    mcp.tool(annotations=annotations, structured_output=False)(_instrument(function))
    return function


def _read_tool[F: Callable[..., Any]](
    annotations: ToolAnnotations = _READ_ONLY,
) -> Callable[[F], F]:
    """Register a tool that only reads from Deck."""
    return lambda function: _register_tool(function, annotations, writes=False)


def _write_tool[F: Callable[..., Any]](
    annotations: ToolAnnotations,
) -> Callable[[F], F]:
    """Register a state-changing tool so the tool policy can remove it."""
    return lambda function: _register_tool(function, annotations, writes=True)


def disabled_tools(config: DeckConfig) -> set[str]:
    """Return the tools that MCP_READ_ONLY and MCP_ENABLED_TOOLS rule out."""
    enabled = config.enabled_tools
    if enabled is not None and (unknown := enabled - _TOOL_NAMES):
        raise ValueError(
            f"MCP_ENABLED_TOOLS lists unknown tools: {sorted(unknown)}. "
            f"Available tools: {sorted(_TOOL_NAMES)}"
        )
    disabled: set[str] = set()
    if config.read_only:
        disabled |= _WRITE_TOOL_NAMES
    if enabled is not None:
        disabled |= _TOOL_NAMES - enabled
    return disabled


def _apply_tool_policy(app: FastMCP, config: DeckConfig) -> None:
    disabled = disabled_tools(config)
    for name in sorted(disabled):
        with suppress(ToolError):
            app.remove_tool(name)
    if disabled:
        logger.info("Tool policy disabled: %s", ", ".join(sorted(disabled)))


def _authorize_write(runtime: DeckRuntime, tool: str, **ids: object) -> None:
    """Refuse writes in read-only mode and log an audit line for allowed ones.

    The audit line carries the tool name and identifiers only, never card
    content or credentials.
    """
    if runtime.config.read_only:
        raise ValueError(f"{tool} is disabled because MCP_READ_ONLY is set")
    enabled = runtime.config.enabled_tools
    if enabled is not None and tool not in enabled:
        raise ValueError(f"{tool} is not listed in MCP_ENABLED_TOOLS")
    audit_logger.info(
        "write tool=%s %s", tool, " ".join(f"{k}={v}" for k, v in ids.items())
    )


def _resolve_text_field(value: str | None, current: str | None) -> str:
    if value is None:
        return current or ""
    return value


def _resolve_datetime_field(value: str | None, current: str | None) -> str | None:
    if value is None:
        return current
    if value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "Datetime fields must be ISO-8601 timestamps like "
            "'2026-04-02T00:00:00+00:00'; use '' to clear or None to keep current."
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(
            "Datetime fields must be ISO-8601 timestamps like "
            "'2026-04-02T00:00:00+00:00'; use '' to clear or None to keep current."
        )
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


def _summarize_card(card: Card) -> CardSummary:
    return CardSummary(
        id=card.id,
        title=card.title,
        stackId=card.stackId,
        duedate=card.duedate,
        done=card.done,
        archived=bool(card.archived),
        labels=[label.title for label in card.labels or [] if label.title],
        assignees=[
            assignment.participant.uid
            for assignment in card.assignedUsers or []
            if assignment.participant is not None and assignment.participant.uid
        ],
    )


def _card_matches_done_filter(card: Card, done: bool | None) -> bool:
    if done is None:
        return True
    # Card.done is an ISO-8601 datetime string or None, not a boolean.
    return (card.done is not None) is done


@_read_tool()
async def list_boards() -> list[Board]:
    """List all boards the authenticated user can access.

    Returns board metadata including IDs and labels. Use this to discover board
    IDs before calling board-specific tools.
    """
    runtime = get_runtime()
    response = await make_nc_request(runtime.client, runtime.config, "GET", "/boards")
    return [Board.model_validate(board) for board in response]


@_read_tool()
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


@_read_tool()
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


@_read_tool()
async def list_cards(
    board_id: int,
    stack_id: int,
    done: Annotated[
        bool | None,
        Field(
            description=(
                "Filter: True=only done cards, False=only open cards, None=all."
            )
        ),
    ] = None,
    compact: Annotated[bool, Field(description=_COMPACT_DESCRIPTION)] = False,
) -> list[Card] | list[CardSummary]:
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
            cards = [
                card
                for card in stack.cards or []
                if _card_matches_done_filter(card, done)
            ]
            return [_summarize_card(card) for card in cards] if compact else cards
    raise ValueError(f"Stack {stack_id} not found on board {board_id}")


async def _collect_board_cards(
    runtime: DeckRuntime,
    semaphore: asyncio.Semaphore,
    board_id: int,
    board_title: str,
    user_id: str,
    done: bool | None,
    compact: bool,
) -> tuple[list[CardResult], SkippedBoard | None]:
    """Fetch one board's stacks and return the cards assigned to the user."""
    async with semaphore:
        try:
            stacks_response = await make_nc_request(
                runtime.client,
                runtime.config,
                "GET",
                f"/boards/{board_id}/stacks",
            )
        except DeckHTTPError as error:
            if error.status_code not in _SKIPPABLE_BOARD_STATUS_CODES:
                raise
            reason = f"HTTP {error.status_code}"
            return [], SkippedBoard(board_id=board_id, reason=reason)

    results: list[CardResult] = []
    for stack_data in stacks_response:
        stack = Stack.model_validate(stack_data)
        if stack.id is None:
            continue
        for card in stack.cards or []:
            if not _card_is_assigned_to_user(card, user_id):
                continue
            if not _card_matches_done_filter(card, done):
                continue
            results.append(
                CardResult(
                    board_id=board_id,
                    board_title=board_title,
                    stack_id=stack.id,
                    stack_title=stack.title or "",
                    card=_summarize_card(card) if compact else card,
                )
            )
    return results, None


@_read_tool()
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
                "Filter: True=only done cards, False=only open cards, None=all."
            )
        ),
    ] = None,
    compact: Annotated[bool, Field(description=_COMPACT_DESCRIPTION)] = False,
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_ASSIGNED_CARDS_LIMIT,
            description=(
                "Maximum number of cards to return. total_matches and truncated "
                "report whether more cards matched."
            ),
        ),
    ] = DEFAULT_ASSIGNED_CARDS_LIMIT,
) -> AssignedCards:
    """Find cards assigned to a user across boards.

    Filters by user, board, and done status, and returns board and stack context
    with each card. Boards are fetched concurrently. Boards that answer 403 or
    404 are listed in skipped_boards instead of failing the whole search. At most
    limit cards are returned; truncated says whether more matched. Prefer this
    over list_stacks plus manual filtering.
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

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BOARD_REQUESTS)
    tasks = [
        asyncio.create_task(
            _collect_board_cards(
                runtime,
                semaphore,
                board_id,
                board_title,
                resolved_user_id,
                done,
                compact,
            )
        )
        for board_id, board_title in boards_to_query
    ]
    try:
        outcomes = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        raise

    results = [card for cards, _ in outcomes for card in cards]
    skipped = [board for _, board in outcomes if board is not None]
    return AssignedCards(
        cards=results[:limit],
        skipped_boards=skipped,
        total_matches=len(results),
        truncated=len(results) > limit,
    )


@_write_tool(_CREATE)
async def create_card(
    board_id: int,
    stack_id: int,
    title: Annotated[str, Field(max_length=MAX_TITLE_LENGTH)],
    description: Annotated[
        str,
        Field(
            description="Card description. Defaults to empty.",
            max_length=MAX_DESCRIPTION_LENGTH,
        ),
    ] = "",
) -> Card:
    """Create a new card in a stack.

    Returns the created card.
    """
    runtime = get_runtime()
    _authorize_write(runtime, "create_card", board_id=board_id, stack_id=stack_id)
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


@_read_tool()
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


@_write_tool(_DESTRUCTIVE)
async def update_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    title: Annotated[
        str | None,
        Field(
            description="New title. None to keep current.",
            max_length=MAX_TITLE_LENGTH,
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(
            description="New description text, '' to clear, None to keep current.",
            max_length=MAX_DESCRIPTION_LENGTH,
        ),
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
    ISO-8601 datetime string to set a new value. The Deck API has no conditional
    update, so a concurrent edit made between the fetch and the write can be
    overwritten.
    """
    runtime = get_runtime()
    _authorize_write(
        runtime, "update_card", board_id=board_id, stack_id=stack_id, card_id=card_id
    )
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
        "order": order
        if order is not None
        else (current_card.order if current_card.order is not None else 0),
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


@_write_tool(_ADDITIVE)
async def move_card(
    board_id: int,
    card_id: int,
    target_stack_name: Annotated[
        str | None,
        Field(description="Name of the destination stack. Case-insensitive."),
    ] = None,
    target_stack_id: Annotated[
        int | None,
        Field(
            description=(
                "ID of the destination stack. Use it when several stacks share a "
                "name; takes precedence over target_stack_name."
            )
        ),
    ] = None,
) -> Card:
    """Move a card to a different stack on the same board.

    Provide target_stack_name or target_stack_id. Name matching is
    case-insensitive. If no stack matches, the error lists the available
    stacks; if several match, the error lists their IDs.
    """
    if target_stack_name is None and target_stack_id is None:
        raise ValueError("Provide target_stack_name or target_stack_id")

    runtime = get_runtime()
    _authorize_write(runtime, "move_card", board_id=board_id, card_id=card_id)
    stacks_data = await make_nc_request(
        runtime.client,
        runtime.config,
        "GET",
        f"/boards/{board_id}/stacks",
    )
    stacks = [Stack.model_validate(stack_data) for stack_data in stacks_data]

    current_stack_id: int | None = None
    current_card_order: int | None = None
    for stack in stacks:
        for card in stack.cards or []:
            if card.archived:
                continue
            if card.id == card_id and stack.id is not None:
                current_stack_id = stack.id
                current_card_order = card.order

    if target_stack_id is not None:
        matching_ids = [
            stack.id
            for stack in stacks
            if stack.id is not None and stack.id == target_stack_id
        ]
    else:
        wanted_name = (target_stack_name or "").lower()
        matching_ids = [
            stack.id
            for stack in stacks
            if stack.title
            and stack.id is not None
            and stack.title.lower() == wanted_name
        ]

    if not matching_ids:
        available_stacks = ", ".join(
            f"{stack.title or '<untitled>'} (id {stack.id})" for stack in stacks
        )
        requested = (
            f"ID {target_stack_id}"
            if target_stack_id is not None
            else f"'{target_stack_name}'"
        )
        raise ValueError(
            f"Stack {requested} not found. Available stacks: {available_stacks}"
        )
    if len(matching_ids) > 1:
        raise ValueError(
            f"Stack name '{target_stack_name}' is ambiguous (stack IDs: "
            f"{', '.join(str(stack_id) for stack_id in matching_ids)}). "
            "Pass target_stack_id instead."
        )
    target_stack_id = matching_ids[0]

    if current_stack_id is None:
        raise ValueError(f"Card with ID {card_id} not found on board {board_id}")

    payload = {
        "stackId": target_stack_id,
        "order": current_card_order if current_card_order is not None else 999,
    }
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{target_stack_id}/cards/{card_id}/reorder",
        json=payload,
    )

    async def fetch_from_target_stack() -> Card:
        try:
            refreshed = await make_nc_request(
                runtime.client,
                runtime.config,
                "GET",
                f"/boards/{board_id}/stacks/{target_stack_id}/cards/{card_id}",
            )
        except DeckHTTPError as error:
            raise ValueError(
                f"Card {card_id} could not be verified in target stack "
                f"{target_stack_id} after reorder"
            ) from error

        refreshed_card = Card.model_validate(refreshed)
        if refreshed_card.id != card_id or refreshed_card.stackId != target_stack_id:
            raise ValueError(
                f"Card {card_id} was not moved to stack {target_stack_id}; "
                f"refreshed card id={refreshed_card.id}, "
                f"stackId={refreshed_card.stackId}"
            )
        return refreshed_card

    if isinstance(response, list):
        if not response:
            raise ValueError("Empty list response from card reorder endpoint")
        # The reorder endpoint returns all affected cards; find ours by ID.
        for item in response:
            validated = Card.model_validate(item)
            if validated.id == card_id:
                if validated.stackId != target_stack_id:
                    return await fetch_from_target_stack()
                return validated
        # Card not in response list — fetch it directly.
        return await fetch_from_target_stack()

    validated_response = Card.model_validate(response)
    if validated_response.stackId != target_stack_id:
        return await fetch_from_target_stack()
    return validated_response


@_write_tool(_ADDITIVE)
async def archive_card(board_id: int, stack_id: int, card_id: int) -> Card:
    """Archive a card.

    Archived cards are removed from the active board view.
    """
    runtime = get_runtime()
    _authorize_write(
        runtime, "archive_card", board_id=board_id, stack_id=stack_id, card_id=card_id
    )
    response = await make_nc_request(
        runtime.client,
        runtime.config,
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/archive",
    )
    return Card.model_validate(response)


@_write_tool(_DESTRUCTIVE)
async def remove_label_from_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    label_id: int,
) -> dict[str, Any]:
    """Remove a label from a card."""
    runtime = get_runtime()
    _authorize_write(
        runtime,
        "remove_label_from_card",
        board_id=board_id,
        stack_id=stack_id,
        card_id=card_id,
        label_id=label_id,
    )
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


@_write_tool(_ADDITIVE)
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
    _authorize_write(
        runtime,
        "assign_label_to_card",
        board_id=board_id,
        stack_id=stack_id,
        card_id=card_id,
        label_id=label_id,
    )
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


@_write_tool(_ADDITIVE)
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
    _authorize_write(
        runtime,
        "assign_user_to_card",
        board_id=board_id,
        stack_id=stack_id,
        card_id=card_id,
        user_id=user_id,
    )
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


@_write_tool(_DESTRUCTIVE)
async def unassign_user_from_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    user_id: str,
) -> dict[str, Any]:
    """Remove a user assignment from a card."""
    runtime = get_runtime()
    _authorize_write(
        runtime,
        "unassign_user_from_card",
        board_id=board_id,
        stack_id=stack_id,
        card_id=card_id,
        user_id=user_id,
    )
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
