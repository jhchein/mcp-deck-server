import asyncio, httpx, json
from mcp_deck_server.config import load_config
from mcp_deck_server.client import make_nc_request

STACKS = {41: 'Offen', 42: 'Do Now', 43: 'Schedule', 44: 'Delegate/Automate', 45: 'Drop/Ignore', 46: 'Parked/Blocked', 48: 'Scheduled', 49: 'Delegated/UATs'}

async def get_card_details(board_id: int, card_ids: list):
    config = load_config()
    async with httpx.AsyncClient(
        timeout=config.request_timeout,
        auth=(config.nc_user, config.nc_app_password),
        headers={'OCS-APIRequest': 'true', 'Content-Type': 'application/json', 'Accept': 'application/json'},
    ) as client:
        # First get all stacks with cards to find stack_id for each card
        stacks = await make_nc_request(client, config, 'GET', f'/boards/{board_id}/stacks')
        card_to_stack = {}
        for stack in stacks:
            for card in stack.get('cards', []):
                card_to_stack[card['id']] = stack['id']
        
        print('=== Card Details ===')
        for card_id in card_ids:
            stack_id = card_to_stack.get(card_id)
            if stack_id:
                card = await make_nc_request(client, config, 'GET', f'/boards/{board_id}/stacks/{stack_id}/cards/{card_id}')
                labels = ', '.join([l['title'] for l in card.get('labels', [])]) if card.get('labels') else 'None'
                stack_title = STACKS.get(card.get('stackId'), 'Unknown')
                print(f"---")
                print(f"Card ID: {card['id']}")
                print(f"Title: {card['title']}")
                print(f"Stack ID: {card.get('stackId')}, Stack: {stack_title}")
                print(f"Done: {card.get('done')}")
                print(f"Due Date: {card.get('duedate')}")
                print(f"Labels: {labels}")
                print(f"Description: {card.get('description', '(none)')}")
            else:
                print(f"---")
                print(f"Card ID: {card_id} - NOT FOUND in any stack")

card_ids = [628, 666, 652, 665, 629, 553, 371, 647, 646, 649]
asyncio.run(get_card_details(8, card_ids))
