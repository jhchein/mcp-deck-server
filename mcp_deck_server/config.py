from __future__ import annotations

import dataclasses
import os

from dotenv import load_dotenv


@dataclasses.dataclass(frozen=True)
class DeckConfig:
    nc_url: str
    nc_user: str
    nc_app_password: str = dataclasses.field(repr=False)
    nc_api_version: str = "v1.1"
    request_timeout: float = 30.0


def load_config() -> DeckConfig:
    load_dotenv()

    nc_url = os.getenv("NC_URL", "").strip()
    nc_user = os.getenv("NC_USER", "").strip()
    nc_app_password = os.getenv("NC_APP_PASSWORD", "").strip()
    nc_api_version = os.getenv("NC_API_VERSION", "v1.1").strip() or "v1.1"
    request_timeout_raw = os.getenv("MCP_REQUEST_TIMEOUT", "30.0").strip() or "30.0"

    if not nc_url:
        raise ValueError("NC_URL is required")
    if not nc_user:
        raise ValueError("NC_USER is required")
    if not nc_app_password:
        raise ValueError("NC_APP_PASSWORD is required")

    try:
        request_timeout = float(request_timeout_raw)
    except ValueError as error:
        raise ValueError("MCP_REQUEST_TIMEOUT must be a valid number") from error

    if request_timeout <= 0:
        raise ValueError("MCP_REQUEST_TIMEOUT must be greater than 0")

    return DeckConfig(
        nc_url=nc_url.rstrip("/"),
        nc_user=nc_user,
        nc_app_password=nc_app_password,
        nc_api_version=nc_api_version,
        request_timeout=request_timeout,
    )
