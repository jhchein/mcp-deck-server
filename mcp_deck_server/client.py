from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .config import DeckConfig

RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
RETRY_BASE_DELAY_SECONDS = 0.5
RETRY_MAX_DELAY_SECONDS = 5.0
MAX_ERROR_DETAIL_CHARS = 300


class DeckAPIError(Exception):
    pass


def _extract_error_detail(body: str) -> str | None:
    """Return Deck's error message from a JSON error body, if present.

    Non-JSON bodies (for example HTML error pages) are never echoed so that
    markup and server internals do not reach the MCP client.
    """
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if not isinstance(message, str):
        return None
    collapsed = " ".join(message.split())
    if not collapsed:
        return None
    if len(collapsed) > MAX_ERROR_DETAIL_CHARS:
        return collapsed[: MAX_ERROR_DETAIL_CHARS - 1] + "…"
    return collapsed


class DeckHTTPError(DeckAPIError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        message = f"Deck API HTTP error {status_code}"
        detail = _extract_error_detail(body)
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


class DeckConnectionError(DeckAPIError):
    def __init__(self, message: str):
        super().__init__(message)


class DeckResponseError(DeckAPIError):
    """The Deck API answered successfully but with an unusable body."""


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            return min(float(retry_after), RETRY_MAX_DELAY_SECONDS)
    return min(RETRY_BASE_DELAY_SECONDS * 2**attempt, RETRY_MAX_DELAY_SECONDS)


async def _send_with_retries(
    client: httpx.AsyncClient,
    config: DeckConfig,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Send a request, retrying transient failures for idempotent GETs only."""
    max_retries = config.max_retries if method.upper() == "GET" else 0

    for attempt in range(max_retries + 1):
        is_last_attempt = attempt == max_retries
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as error:
            if is_last_attempt:
                raise DeckConnectionError("Deck API connection error") from error
            await asyncio.sleep(_retry_delay(attempt, None))
            continue
        except httpx.RequestError as error:
            raise DeckConnectionError("Deck API connection error") from error

        if response.status_code in RETRYABLE_STATUS_CODES and not is_last_attempt:
            await asyncio.sleep(_retry_delay(attempt, response))
            continue
        return response

    raise AssertionError("unreachable")  # pragma: no cover


async def make_nc_request(
    client: httpx.AsyncClient,
    config: DeckConfig,
    method: str,
    endpoint: str,
    **kwargs: Any,
) -> Any:
    url = f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}{endpoint}"

    response = await _send_with_retries(client, config, method, url, **kwargs)

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise DeckHTTPError(error.response.status_code, error.response.text) from error

    if response.status_code == 204:
        return None

    try:
        return response.json()
    except ValueError as error:
        raise DeckResponseError("Deck API returned a non-JSON response") from error
