import asyncio, httpx, json
from mcp_deck_server.config import load_config
from mcp_deck_server.client import make_nc_request

async def get_board_stacks(board_id: int):
    config = load_config()
    async with httpx.AsyncClient(
        timeout=config.request_timeout,
        auth=(config.nc_user, config.nc_app_password),
        headers={'OCS-APIRequest': 'true', 'Content-Type': 'application/json', 'Accept': 'application/json'},
    ) as client:
        stacks = await make_nc_request(client, config, 'GET', f'/boards/{board_id}/stacks')
        print('=== Board 8 Stacks ===')
        for stack in stacks:
            print(f"Stack ID: {stack['id']}, Title: {stack['title']}")
        return {s['id']: s['title'] for s in stacks}

asyncio.run(get_board_stacks(8))
