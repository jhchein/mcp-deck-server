from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mcp.types import TextContent

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict | list:
    fixture_path = FIXTURES_DIR / name
    with fixture_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def text_payload(result: Sequence[Any] | dict[str, Any]) -> Any:
    """Parse the JSON text block of a FastMCP ``call_tool`` result."""
    assert not isinstance(result, dict), "expected unstructured content blocks"
    block = result[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)
