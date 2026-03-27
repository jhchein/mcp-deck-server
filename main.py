from mcp_deck_server import mcp
from mcp_deck_server.config import load_config

if __name__ == "__main__":
    config = load_config()
    mcp.run(transport=config.transport)
