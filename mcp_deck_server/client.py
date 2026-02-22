from __future__ import annotations

from typing import Any

import httpx

from .config import DeckConfig


class DeckAPIError(Exception):
    pass


class DeckHTTPError(DeckAPIError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Deck API HTTP error {status_code}")


class DeckConnectionError(DeckAPIError):
    def __init__(self, message: str):
        super().__init__(message)


async def make_nc_request(
    client: httpx.AsyncClient,
    config: DeckConfig,
    method: str,
    endpoint: str,
    **kwargs: Any,
) -> Any:
    url = f"{config.nc_url}/index.php/apps/deck/api/{config.nc_api_version}{endpoint}"

    try:
        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise DeckHTTPError(error.response.status_code, error.response.text) from error
    except (httpx.TimeoutException, httpx.RequestError) as error:
        raise DeckConnectionError(str(error)) from error

    if response.status_code == 204:
        return None

    return response.json()
