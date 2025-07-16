import os
from typing import Any, Dict, List

import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("deck")

# Constants from environment variables
NC_URL = os.getenv("NC_URL")
NC_USER = os.getenv("NC_USER")
NC_APP_PASSWORD = os.getenv("NC_APP_PASSWORD")
NC_API_VERSION = "v1.1"  # Specify the Deck API version

# Basic auth tuple
auth = (NC_USER, NC_APP_PASSWORD) if NC_USER and NC_APP_PASSWORD else None

# Headers for API requests
headers = {
    "OCS-APIRequest": "true",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# Helper function to make Nextcloud API requests
async def make_nc_request(method: str, endpoint: str, **kwargs) -> Any:
    """Make a request to the Nextcloud Deck API."""
    if not auth:
        raise ValueError("Nextcloud credentials not found in .env file.")

    url = f"{NC_URL}/index.php/apps/deck/api/{NC_API_VERSION}{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method, url, auth=auth, headers=headers, **kwargs
            )
            response.raise_for_status()
            if response.status_code == 204:  # No Content
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP error: {e.response.status_code} - {e.response.text}"
            }
        except httpx.RequestError as e:
            return {"error": f"Request error: {e}"}


@mcp.tool()
async def list_boards() -> List[Dict[str, Any]]:
    """List all Nextcloud Deck boards."""
    return await make_nc_request("GET", "/boards")


@mcp.tool()
async def get_board(board_id: int) -> Dict[str, Any]:
    """Get details for a specific board."""
    return await make_nc_request("GET", f"/boards/{board_id}")


@mcp.tool()
async def list_stacks(board_id: int) -> List[Dict[str, Any]]:
    """List all stacks for a given board ID."""
    return await make_nc_request("GET", f"/boards/{board_id}/stacks")


@mcp.tool()
async def list_cards(board_id: int, stack_id: int) -> List[Dict[str, Any]]:
    """List all cards in a specific stack on a board."""
    return await make_nc_request("GET", f"/boards/{board_id}/stacks/{stack_id}/cards")


@mcp.tool()
async def create_card(
    board_id: int, stack_id: int, title: str, description: str = ""
) -> Dict[str, Any]:
    """Create a new card in a specific stack on a board."""
    payload = {
        "title": title,
        "description": description,
        "type": "plain",
    }
    return await make_nc_request(
        "POST", f"/boards/{board_id}/stacks/{stack_id}/cards", json=payload
    )


@mcp.tool()
async def get_card(board_id: int, stack_id: int, card_id: int) -> Dict[str, Any]:
    """Get details of a specific card."""
    return await make_nc_request(
        "GET", f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}"
    )


@mcp.tool()
async def update_card(
    board_id: int,
    stack_id: int,
    card_id: int,
    title: str = None,
    description: str = None,
    duedate: str = None,
    type: str = "plain",  # Add type parameter with a default value
) -> Dict[str, Any]:
    """Update a card on a board."""
    # If title is not provided, fetch the current card to get the existing title
    if title is None:
        current_card = await make_nc_request(
            "GET", f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}"
        )
        if isinstance(current_card, dict) and "title" in current_card:
            title = current_card["title"]
        else:
            return {"error": "Could not fetch current card title"}

    payload = {
        k: v
        for k, v in {
            "title": title,
            "description": description,
            "duedate": duedate,
            "type": type,
        }.items()
        if v is not None
    }
    return await make_nc_request(
        "PUT", f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}", json=payload
    )


@mcp.tool()
async def move_card(
    board_id: int, card_id: int, target_stack_name: str
) -> Dict[str, Any]:
    """Move a card to a different stack (e.g., "Done", "Doing", "Backlog")."""
    all_stacks = await list_stacks(board_id)
    if isinstance(all_stacks, dict) and "error" in all_stacks:
        return all_stacks

    target_stack_id = None
    current_stack_id = None
    current_card = None

    for stack in all_stacks:
        if stack["title"].lower() == target_stack_name.lower():
            target_stack_id = stack["id"]
        if "cards" in stack:
            for card in stack["cards"]:
                # skip archived cards
                if card.get("archived", False):
                    continue
                if card["id"] == card_id:
                    current_stack_id = stack["id"]
                    current_card = card
                    break
        if current_stack_id and target_stack_id:
            break

    if not target_stack_id:
        return {
            "error": f"Stack '{target_stack_name}' not found. Viable stacks: {', '.join(stack['title'] for stack in all_stacks)}."
        }
    if not current_stack_id or not current_card:
        return {"error": f"Card with ID {card_id} not found on board {board_id}."}

    payload = {"stackId": target_stack_id, "order": current_card.get("order", 999)}
    return await make_nc_request(
        "PUT",
        f"/boards/{board_id}/stacks/{current_stack_id}/cards/{card_id}/reorder",
        json=payload,
    )


@mcp.tool()
async def archive_card(board_id: int, stack_id: int, card_id: int) -> Dict[str, Any]:
    """Archives a card."""
    payload = {"archived": True}
    return await make_nc_request(
        "PUT", f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}", json=payload
    )


@mcp.tool()
async def remove_label_from_card(
    board_id: int, stack_id: int, card_id: int, label_id: int
) -> Dict[str, Any]:
    """Remove a label from a card."""
    payload = {"labelId": label_id}
    return await make_nc_request(
        "PUT",
        f"/boards/{board_id}/stacks/{stack_id}/cards/{card_id}/removeLabel",
        json=payload,
    )


if __name__ == "__main__":
    # Run the server with: `uv run main.py`
    mcp.run(transport="stdio")
