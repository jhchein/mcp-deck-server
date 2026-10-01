from __future__ import annotations

import dataclasses

import pytest

from mcp_deck_server.config import load_config


@pytest.mark.parametrize("missing_var", ["NC_URL", "NC_USER", "NC_APP_PASSWORD"])
def test_load_config_missing_required(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv(missing_var, "")

    with pytest.raises(ValueError):
        load_config()


def test_load_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test/")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.delenv("NC_API_VERSION", raising=False)
    monkeypatch.delenv("MCP_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("MCP_MAX_RETRIES", raising=False)

    config = load_config()
    field_names = {field.name for field in dataclasses.fields(config)}

    assert config.nc_url == "https://nextcloud.example.test"
    assert config.nc_api_version == "v1.1"
    assert field_names == {
        "nc_url",
        "nc_user",
        "nc_app_password",
        "nc_api_version",
        "request_timeout",
        "max_retries",
        "read_only",
    }
    assert config.request_timeout == 30.0
    assert config.max_retries == 2
    assert config.read_only is False


def test_load_config_rejects_non_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_URL", "ftp://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")

    with pytest.raises(ValueError, match=r"NC_URL must be an absolute HTTP\(S\) URL"):
        load_config()


def test_load_config_rejects_url_without_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NC_URL", "https:///nextcloud")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")

    with pytest.raises(ValueError, match=r"NC_URL must be an absolute HTTP\(S\) URL"):
        load_config()


@pytest.mark.parametrize(
    "nc_url",
    [
        "https://nextcloud.example.test?token=abc",
        "https://nextcloud.example.test#deck",
    ],
)
def test_load_config_rejects_url_with_query_or_fragment(
    monkeypatch: pytest.MonkeyPatch, nc_url: str
) -> None:
    monkeypatch.setenv("NC_URL", nc_url)
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="NC_URL must not include query or fragment"):
        load_config()


def test_load_config_timeout_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_REQUEST_TIMEOUT", "abc")

    with pytest.raises(ValueError, match="MCP_REQUEST_TIMEOUT"):
        load_config()


def test_load_config_timeout_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_REQUEST_TIMEOUT", "0")

    with pytest.raises(ValueError, match="MCP_REQUEST_TIMEOUT must be greater than 0"):
        load_config()


@pytest.mark.parametrize("raw_value", ["abc", "-1", "6", "1.5"])
def test_load_config_rejects_invalid_max_retries(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_MAX_RETRIES", raw_value)

    with pytest.raises(ValueError, match="MCP_MAX_RETRIES"):
        load_config()


def test_load_config_accepts_zero_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_MAX_RETRIES", "0")

    assert load_config().max_retries == 0


def _set_required_env(monkeypatch: pytest.MonkeyPatch, nc_url: str) -> None:
    monkeypatch.setenv("NC_URL", nc_url)
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.delenv("NC_ALLOW_INSECURE_HTTP", raising=False)
    monkeypatch.delenv("NC_API_VERSION", raising=False)
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)


@pytest.mark.parametrize(
    "nc_url",
    ["http://localhost", "http://127.0.0.1:8080", "http://[::1]:8080/nextcloud"],
)
def test_load_config_allows_http_for_loopback(
    monkeypatch: pytest.MonkeyPatch, nc_url: str
) -> None:
    _set_required_env(monkeypatch, nc_url)

    assert load_config().nc_url == nc_url


def test_load_config_rejects_http_for_remote_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch, "http://nextcloud.example.test")

    with pytest.raises(ValueError, match="must use https"):
        load_config()


def test_load_config_allows_remote_http_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch, "http://nextcloud.example.test")
    monkeypatch.setenv("NC_ALLOW_INSECURE_HTTP", "true")

    assert load_config().nc_url == "http://nextcloud.example.test"


@pytest.mark.parametrize("version", ["v1.1", "v1", "v2.10"])
def test_load_config_accepts_valid_api_versions(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    _set_required_env(monkeypatch, "https://nextcloud.example.test")
    monkeypatch.setenv("NC_API_VERSION", version)

    assert load_config().nc_api_version == version


@pytest.mark.parametrize("version", ["1.1", "v1.1/../x", "v1.", "latest", "v1.1?x=1"])
def test_load_config_rejects_invalid_api_versions(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    _set_required_env(monkeypatch, "https://nextcloud.example.test")
    monkeypatch.setenv("NC_API_VERSION", version)

    with pytest.raises(ValueError, match="NC_API_VERSION"):
        load_config()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("true", True), ("1", True), ("YES", True), ("false", False), ("off", False)],
)
def test_load_config_parses_read_only(
    monkeypatch: pytest.MonkeyPatch, raw_value: str, expected: bool
) -> None:
    _set_required_env(monkeypatch, "https://nextcloud.example.test")
    monkeypatch.setenv("MCP_READ_ONLY", raw_value)

    assert load_config().read_only is expected


def test_load_config_rejects_unparseable_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_env(monkeypatch, "https://nextcloud.example.test")
    monkeypatch.setenv("MCP_READ_ONLY", "maybe")

    with pytest.raises(ValueError, match="MCP_READ_ONLY"):
        load_config()
