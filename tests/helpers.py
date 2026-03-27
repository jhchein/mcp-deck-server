from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict | list:
    fixture_path = FIXTURES_DIR / name
    with fixture_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)
