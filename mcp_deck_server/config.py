from __future__ import annotations

import dataclasses
import os
import re
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclasses.dataclass(frozen=True)
class DeckConfig:
    nc_url: str
    nc_user: str
    nc_app_password: str = dataclasses.field(repr=False)
    nc_api_version: str = "v1.1"
    request_timeout: float = 30.0
    max_retries: int = 2
    read_only: bool = False


MAX_RETRIES_LIMIT = 5
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
API_VERSION_PATTERN = re.compile(r"v\d+(\.\d+)?")
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _parse_bool_env(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in _FALSE_VALUES or not raw:
        return False
    if raw in _TRUE_VALUES:
        return True
    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def load_config() -> DeckConfig:
    load_dotenv()

    nc_url = os.getenv("NC_URL", "").strip()
    nc_user = os.getenv("NC_USER", "").strip()
    nc_app_password = os.getenv("NC_APP_PASSWORD", "").strip()
    nc_api_version = os.getenv("NC_API_VERSION", "v1.1").strip() or "v1.1"
    request_timeout_raw = os.getenv("MCP_REQUEST_TIMEOUT", "30.0").strip() or "30.0"

    if not nc_url:
        raise ValueError("NC_URL is required")
    parsed_nc_url = urlparse(nc_url)
    if parsed_nc_url.scheme not in {"http", "https"} or not parsed_nc_url.netloc:
        raise ValueError("NC_URL must be an absolute HTTP(S) URL")
    if parsed_nc_url.query or parsed_nc_url.fragment:
        raise ValueError("NC_URL must not include query or fragment")
    if (
        parsed_nc_url.scheme == "http"
        and parsed_nc_url.hostname not in LOOPBACK_HOSTS
        and not _parse_bool_env("NC_ALLOW_INSECURE_HTTP")
    ):
        raise ValueError(
            "NC_URL must use https because credentials are sent with every request; "
            "set NC_ALLOW_INSECURE_HTTP=true to allow plain http for a non-local host"
        )
    if not API_VERSION_PATTERN.fullmatch(nc_api_version):
        raise ValueError("NC_API_VERSION must look like 'v1.1'")
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

    max_retries_raw = os.getenv("MCP_MAX_RETRIES", "2").strip() or "2"
    try:
        max_retries = int(max_retries_raw)
    except ValueError as error:
        raise ValueError("MCP_MAX_RETRIES must be an integer") from error
    if not 0 <= max_retries <= MAX_RETRIES_LIMIT:
        raise ValueError(f"MCP_MAX_RETRIES must be between 0 and {MAX_RETRIES_LIMIT}")

    return DeckConfig(
        nc_url=nc_url.rstrip("/"),
        nc_user=nc_user,
        nc_app_password=nc_app_password,
        nc_api_version=nc_api_version,
        request_timeout=request_timeout,
        max_retries=max_retries,
        read_only=_parse_bool_env("MCP_READ_ONLY"),
    )
