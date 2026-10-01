from __future__ import annotations

import httpx
import pytest
import respx

from mcp_deck_server import cli

BOARDS_URL = "https://nextcloud.example.test/index.php/apps/deck/api/v1.1/boards"


@pytest.fixture(autouse=True)
def deck_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_URL", "https://nextcloud.example.test")
    monkeypatch.setenv("NC_USER", "alice")
    monkeypatch.setenv("NC_APP_PASSWORD", "secret")
    monkeypatch.setenv("MCP_MAX_RETRIES", "0")
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("MCP_ENABLED_TOOLS", raising=False)


@pytest.mark.asyncio
async def test_check_succeeds_and_never_prints_the_password(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with respx.mock() as router:
        router.get(BOARDS_URL).mock(return_value=httpx.Response(200, json=[{}, {}]))
        exit_code = await cli.run_check()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "alice (read-write)" in output
    assert "2 boards" in output
    assert "secret" not in output


@pytest.mark.asyncio
async def test_check_reports_read_only_and_disabled_tools(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MCP_READ_ONLY", "true")
    with respx.mock() as router:
        router.get(BOARDS_URL).mock(return_value=httpx.Response(200, json=[]))
        exit_code = await cli.run_check()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "(read-only)" in output
    assert "disabled tools:" in output
    assert "create_card" in output


@pytest.mark.asyncio
async def test_check_fails_on_rejected_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with respx.mock() as router:
        router.get(BOARDS_URL).mock(return_value=httpx.Response(401))
        exit_code = await cli.run_check()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL  Deck API" in output
    assert "NC_APP_PASSWORD" in output


@pytest.mark.asyncio
async def test_check_fails_when_host_is_unreachable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with respx.mock() as router:
        router.get(BOARDS_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
        exit_code = await cli.run_check()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "ConnectTimeout" in output


@pytest.mark.asyncio
async def test_check_fails_on_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MCP_ENABLED_TOOLS", "no_such_tool")

    exit_code = await cli.run_check()

    assert exit_code == 1
    assert "no_such_tool" in capsys.readouterr().out


def test_main_runs_the_check_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check() -> int:
        return 7

    monkeypatch.setattr(cli, "run_check", fake_check)

    assert cli.main(["--check"]) == 7


def test_main_serves_over_stdio_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli.mcp, "run", lambda transport: calls.append(transport))

    assert cli.main([]) == 0
    assert calls == ["stdio"]
