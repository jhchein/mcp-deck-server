from mcp_deck_server.client import make_nc_request
from mcp_deck_server.config import load_config
import httpx
import asyncio

def card_matches_done_filter(card, done):
    if done is None:
        return True
    return (card.get('done') is not None) is done

def card_is_assigned_to_user(card, user_id):
    for assignment in card.get('assignedUsers', []):
        participant = assignment.get('participant')
        if participant is not None and participant.get('uid') == user_id:
            return True
    return False

async def main():
    cfg = load_config()
    user_id = cfg.nc_user  # 'nc_agent'
    print(f"Testing get_assigned_cards with user_id={user_id}, board_ids=[8], done=True")
    print()
    
    async with httpx.AsyncClient(
        timeout=cfg.request_timeout,
        auth=(cfg.nc_user, cfg.nc_app_password),
        headers={
            'OCS-APIRequest': 'true',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
    ) as client:
        board_id = 8
        
        # Replicate get_assigned_cards logic
        stacks_data = await make_nc_request(client, cfg, 'GET', f'/boards/{board_id}/stacks')
        
        all_assigned_cards = []
        all_cards_in_board = []
        
        for stack in stacks_data:
            stack_id = stack['id']
            stack_title = stack['title']
            cards = stack.get('cards', [])
            
            for card in cards:
                all_cards_in_board.append(card)
                if card_is_assigned_to_user(card, user_id) and card_matches_done_filter(card, True):
                    all_assigned_cards.append((card, stack_id, stack_title))
        
        print(f"Total cards in board 8: {len(all_cards_in_board)}")
        print(f"get_assigned_cards(user_id='{user_id}', board_ids=[8], done=True): {len(all_assigned_cards)} cards")
        
        # Check specifically for cards 646 and 649
        card_646_assigned = any(card_is_assigned_to_user(c, user_id) for c in all_cards_in_board if c['id'] == 646)
        card_649_assigned = any(card_is_assigned_to_user(c, user_id) for c in all_cards_in_board if c['id'] == 649)
        
        print()
        print(f"Card 646 is assigned to user '{user_id}': {card_646_assigned}")
        print(f"Card 649 is assigned to user '{user_id}': {card_649_assigned}")
        
        # Verify card 646 and 649 assignedUsers
        for c in all_cards_in_board:
            if c['id'] in [646, 649]:
                print(f"Card {c['id']} assignedUsers: {c.get('assignedUsers', [])}")
        
        # Report if cards 646/649 are included in get_assigned_cards result
        result_card_ids = [c[0]['id'] for c in all_assigned_cards]
        print()
        print(f"Card 646 in get_assigned_cards result: {646 in result_card_ids}")
        print(f"Card 649 in get_assigned_cards result: {649 in result_card_ids}")
        
        print()
        print("=== All returned cards from get_assigned_cards(done=True) ===")
        for card, stack_id, stack_title in all_assigned_cards:
            print(f"  Card {card['id']}: {card['title'][:50]} (stack {stack_id})")

asyncio.run(main())
