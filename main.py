from mcp_deck_server.config import load_config
from mcp_deck_server.server import mcp


if __name__ == "__main__":
    config = load_config()
    mcp.run(transport=config.transport)
