from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .config import DeckConfig

RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
RETRY_BASE_DELAY_SECONDS = 0.5
RETRY_MAX_DELAY_SECONDS = 5.0
MAX_ERROR_DETAIL_CHARS = 300

logger = logging.getLogger(__name__)
AUTH_FAILURE_HINT = "check NC_USER and NC_APP_PASSWORD"


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
        if status_code == 401:
            message = f"{message} ({AUTH_FAILURE_HINT})"
        super().__init__(message)


class DeckConnectionError(DeckAPIError):
    def __init__(self, message: str):
        super().__init__(message)


class DeckResponseError(DeckAPIError):
    """The Deck API answered successfully but with an unusable body."""


class DeckTimeoutError(DeckAPIError):
    """A tool call ran past its overall deadline (MCP_TOOL_TIMEOUT)."""


def _connection_message(error: httpx.RequestError) -> str:
    # The exception class (ConnectTimeout, ConnectError, ...) helps diagnosis;
    # its text can embed URLs, so it is not echoed.
    return f"Deck API connection error ({type(error).__name__})"


def _parse_retry_after(value: str) -> float | None:
    """Return the wait in seconds from a Retry-After header (seconds or date)."""
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        return None
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """Wait before the next attempt: Retry-After if sent, else jittered backoff.

    Jitter keeps the concurrent board requests of one search from retrying in
    lockstep against a server that is already struggling.
    """
    if response is not None:
        retry_after = _parse_retry_after(response.headers.get("Retry-After", ""))
        if retry_after is not None:
            return min(retry_after, RETRY_MAX_DELAY_SECONDS)
    backoff = min(RETRY_BASE_DELAY_SECONDS * 2**attempt, RETRY_MAX_DELAY_SECONDS)
    return backoff * random.uniform(0.5, 1.0)


async def _wait_before_retry(
    method: str,
    url: str,
    attempt: int,
    response: httpx.Response | None,
    reason: str,
) -> None:
    delay = _retry_delay(attempt, response)
    logger.warning(
        "deck_retry method=%s path=%s attempt=%d reason=%s wait_ms=%.0f",
        method,
        urlsplit(url).path,
        attempt + 1,
        reason,
        delay * 1000,
    )
    await asyncio.sleep(delay)


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
                raise DeckConnectionError(_connection_message(error)) from error
            await _wait_before_retry(method, url, attempt, None, type(error).__name__)
            continue
        except httpx.RequestError as error:
            raise DeckConnectionError(_connection_message(error)) from error

        if response.status_code in RETRYABLE_STATUS_CODES and not is_last_attempt:
            await _wait_before_retry(
                method, url, attempt, response, f"HTTP {response.status_code}"
            )
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
