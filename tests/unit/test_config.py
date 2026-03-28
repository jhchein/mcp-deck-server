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
    }
    assert config.request_timeout == 30.0


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
