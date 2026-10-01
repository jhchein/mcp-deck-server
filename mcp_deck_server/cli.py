"""Command line entry point: run the stdio server or verify the setup."""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Sequence

from .client import DeckAPIError, make_nc_request
from .config import load_config
from .server import create_http_client, disabled_tools, mcp


async def run_check() -> int:
    """Verify configuration and Deck access; return a process exit code."""
    try:
        config = load_config()
        disabled = disabled_tools(config)
    except ValueError as error:
        print(f"FAIL  configuration: {error}")
        return 1

    mode = "read-only" if config.read_only else "read-write"
    print(f"OK    configuration: {config.nc_url} as {config.nc_user} ({mode})")
    if disabled:
        print(f"INFO  disabled tools: {', '.join(sorted(disabled))}")

    async with create_http_client(config) as client:
        started = time.perf_counter()
        try:
            boards = await make_nc_request(client, config, "GET", "/boards")
        except DeckAPIError as error:
            print(f"FAIL  Deck API: {error}")
            return 1
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"OK    Deck API reachable: {len(boards)} boards in {elapsed_ms:.0f} ms")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-deck-server",
        description="MCP server for Nextcloud Deck (stdio transport).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the configuration, test the Deck connection, then exit",
    )
    args = parser.parse_args(argv)
    if args.check:
        return asyncio.run(run_check())
    mcp.run(transport="stdio")
    return 0
