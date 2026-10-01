from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, TextContent

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict | list:
    fixture_path = FIXTURES_DIR / name
    with fixture_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def text_payload(result: Any) -> Any:
    """Parse the JSON text block of an ``MCPServer.call_tool`` result."""
    assert isinstance(result, CallToolResult)
    assert result.structured_content is None, "expected unstructured output"
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)
