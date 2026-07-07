"""Regression tests for the adversarial-review findings (2026-07-06)."""

from __future__ import annotations

import httpx
import pytest

from arborist import client as client_mod
from arborist.client import ScanopyClient, _looks_like_mac
from arborist.config import Config
from arborist.errors import ArboristError
from arborist.server import _transport_security
from arborist.tools import write as write_mod


def make_config(**overrides: str) -> Config:
    env = {
        "SCANOPY_BASE_URL": "http://scanopy.test:60072",
        "SCANOPY_API_KEY": "scp_u_unit-test-key",
        **overrides,
    }
    return Config.from_env(env)


def _mock_client(handler) -> ScanopyClient:
    cfg = make_config()
    c = ScanopyClient(cfg)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=cfg.base_url
    )
    return c


def test_unset_sentinel_is_shared() -> None:
    # A module-local sentinel in write.py made rename-only updates crash: the
    # client's identity check never matched, and the sentinel object leaked
    # into the JSON payload.
    assert write_mod._UNSET is client_mod._UNSET


def test_mac_matching_requires_mac_shape() -> None:
    assert _looks_like_mac("aa:bb:cc:dd:ee:ff")
    assert _looks_like_mac("AA-BB-CC-DD-EE-FF")
    assert _looks_like_mac("aabbccddeeff")
    assert _looks_like_mac("aabb.ccdd.eeff")
    # Selectors whose hex *residue* happens to be 12 chars must not MAC-match.
    assert not _looks_like_mac("unifi-ab12cd34ef56")
    assert not _looks_like_mac("web-01")
    assert not _looks_like_mac("")


async def test_resolve_host_rejects_empty_selector() -> None:
    c = _mock_client(lambda req: pytest.fail("must not reach the network"))
    for sel in ("", "   ", "\t"):
        with pytest.raises(ArboristError, match="must not be empty"):
            await c.resolve_host(sel)
    await c.aclose()


async def test_get_all_paginates_past_old_cap() -> None:
    total = 2500  # above the old silent 2000-record cap

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        offset, limit = int(params["offset"]), int(params["limit"])
        assert limit != 0, "limit=0 (unbounded) must never be sent"
        page = [
            {"id": f"h{i}", "name": f"host-{i}"}
            for i in range(offset, min(offset + limit, total))
        ]
        return httpx.Response(
            200,
            json={"success": True, "data": page, "meta": {}},
            headers={"content-type": "application/json"},
        )

    c = _mock_client(handler)
    items = await c._get_all("/api/v1/hosts")
    assert len(items) == total
    assert items[-1]["name"] == "host-2499"
    await c.aclose()


async def test_get_all_fails_loudly_at_ceiling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        offset, limit = int(params["offset"]), int(params["limit"])
        page = [{"id": f"h{i}"} for i in range(offset, offset + limit)]  # never ends
        return httpx.Response(
            200,
            json={"success": True, "data": page, "meta": {}},
            headers={"content-type": "application/json"},
        )

    c = _mock_client(handler)
    with pytest.raises(ArboristError, match="exceeded 50000 records"):
        await c._get_all("/api/v1/hosts")
    await c.aclose()


def _cfg_no_allowed_hosts() -> Config:
    return make_config()


def test_transport_security_explicit_for_standard_loopback() -> None:
    ts = _transport_security(_cfg_no_allowed_hosts(), "127.0.0.1", 60074)
    assert ts is not None
    assert ts.enable_dns_rebinding_protection
    assert "127.0.0.1:*" in ts.allowed_hosts


def test_transport_security_covers_nonstandard_loopback() -> None:
    # FastMCP's auto-default only fires for 127.0.0.1/localhost/::1; binding
    # 127.0.0.2 with settings=None would silently disable rebinding protection.
    ts = _transport_security(_cfg_no_allowed_hosts(), "127.0.0.2", 60074)
    assert ts is not None
    assert ts.enable_dns_rebinding_protection
    assert "127.0.0.2:*" in ts.allowed_hosts
    assert "http://127.0.0.2:*" in ts.allowed_origins
