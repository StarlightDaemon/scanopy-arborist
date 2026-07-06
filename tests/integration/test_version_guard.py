"""§9 case 1 — the version guard against the live server and a fake future one."""

from __future__ import annotations

import httpx
import pytest

from arborist.client import ScanopyClient
from arborist.compat import MAX_EXCLUSIVE, MIN_SUPPORTED, parse_version
from arborist.config import Config
from arborist.errors import VersionCompatError

pytestmark = pytest.mark.integration


async def test_startup_guard_passes_against_live_server(client: ScanopyClient) -> None:
    result = await client.startup_guard()
    assert result.ok is True
    assert result.reason == "supported"
    assert MIN_SUPPORTED <= parse_version(result.server_version) < MAX_EXCLUSIVE
    assert result.api_version == 1


def _mock_client(env_extra: dict[str, str] | None = None) -> ScanopyClient:
    """A client whose transport answers /api/version with a fake 0.99.0 server.

    The base_url points at a closed local port on purpose: if anything escapes
    the MockTransport, it fails fast instead of touching a real instance.
    """
    env = {
        "SCANOPY_BASE_URL": "http://localhost:59999",
        "SCANOPY_API_KEY": "scp_u_mock-not-a-real-key",
        **(env_extra or {}),
    }
    cfg = Config.from_env(env)
    client = ScanopyClient(cfg)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"api_version": 1, "server_version": "0.99.0"},
                "meta": {"api_version": 1, "server_version": "0.99.0"},
            },
        )

    client._http = httpx.AsyncClient(
        base_url=cfg.base_url, transport=httpx.MockTransport(handler)
    )
    return client


async def test_startup_guard_hard_fails_on_unverified_version() -> None:
    client = _mock_client()
    try:
        with pytest.raises(VersionCompatError) as excinfo:
            await client.startup_guard()
        assert "0.99.0" in str(excinfo.value)
        assert "ARBORIST_ALLOW_UNTESTED_VERSION" in str(excinfo.value)
    finally:
        await client.aclose()


async def test_override_flag_downgrades_hard_fail_to_warning_result() -> None:
    client = _mock_client({"ARBORIST_ALLOW_UNTESTED_VERSION": "true"})
    try:
        result = await client.startup_guard()  # must not raise
        assert result.ok is False
        assert result.server_version == "0.99.0"
        assert "newer than the newest verified" in result.reason
    finally:
        await client.aclose()
