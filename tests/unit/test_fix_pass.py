"""Unit regression tests for the fix pass (findings #2, #3, #6 + tag_usage).

The live behaviors (findings #1, #4, #5, #8 and the SC8 delete_tag fail-closed)
are covered in tests/integration/test_fix_pass_live.py against a real server."""

from __future__ import annotations

import httpx
import pytest

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.errors import ScanopyApiError
from arborist.tools.write import _binding_body, _coerce_bool


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
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=cfg.base_url)
    return c


# ---------------------------------------------------------------- #3 coerce bool


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True), (False, False),
        (1, True), (0, False),
        ("true", True), ("false", False),
        ("True", True), ("FALSE", False),
        (" yes ", True), ("no", False),
        ("on", True), ("off", False),
        ("1", True), ("0", False),
    ],
)
def test_coerce_bool_accepts(value, expected) -> None:
    assert _coerce_bool(value) is expected


@pytest.mark.parametrize("value", ["maybe", "", "  ", 2.5, None, [], {}])
def test_coerce_bool_rejects_ambiguous(value) -> None:
    # The original bug: bool("false") is True. Anything not clearly boolean must
    # raise so the plan and apply phases can never disagree.
    with pytest.raises(ValueError, match="must be a boolean"):
        _coerce_bool(value)


# ---------------------------------------------------------------- #6 binding body


def test_binding_ipaddress_rejects_port_id() -> None:
    with pytest.raises(ValueError, match="does not take a port_id"):
        _binding_body("svc", "IPAddress", port_id="p1", ip_address_id="ip1")


def test_binding_ipaddress_ok_without_port() -> None:
    body = _binding_body("svc", "IPAddress", port_id=None, ip_address_id="ip1")
    assert body == {"service_id": "svc", "type": "IPAddress", "ip_address_id": "ip1"}


def test_binding_port_requires_port_id() -> None:
    with pytest.raises(ValueError, match="requires port_id"):
        _binding_body("svc", "Port", port_id=None, ip_address_id="ip1")


# ---------------------------------------------------- #2 text/plain 4xx handling


def test_text_plain_4xx_surfaces_real_message() -> None:
    # Scanopy answers serde/path-param errors as text/plain; the real message
    # must reach the caller, not the false "endpoint does not exist" hint.
    msg = ("Failed to deserialize the JSON body into the target type: hidden: "
           'invalid type: string "false", expected a boolean')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text=msg, headers={"content-type": "text/plain"})

    async def go() -> None:
        c = _mock_client(handler)
        with pytest.raises(ScanopyApiError) as exc:
            await c._request("PUT", "/api/v1/hosts/x")
        assert exc.value.status == 422
        assert "expected a boolean" in str(exc.value)
        assert "endpoint most likely does not exist" not in str(exc.value)
        await c.aclose()

    import anyio
    anyio.run(go)


def test_text_html_still_reports_missing_endpoint() -> None:
    # A real SPA fallback (text/html) keeps the version-incompatibility hint.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!doctype html><html></html>",
                              headers={"content-type": "text/html"})

    async def go() -> None:
        c = _mock_client(handler)
        with pytest.raises(ScanopyApiError) as exc:
            await c._request("GET", "/api/v1/does-not-exist")
        assert "endpoint most likely does not exist" in str(exc.value)
        await c.aclose()

    import anyio
    anyio.run(go)


# --------------------------------------------------------------- tag_usage (SC8)


def test_tag_usage_finds_cross_network_entities() -> None:
    tag = "tag-1"

    pages = {
        "/api/v1/hosts": [
            {"id": "h1", "name": "in", "network_id": "net-A", "tags": [tag]},
            {"id": "h2", "name": "out", "network_id": "net-B", "tags": [tag]},
            {"id": "h3", "name": "untagged", "network_id": "net-A", "tags": []},
        ],
        "/api/v1/services": [
            {"id": "s1", "name": "svc", "network_id": "net-B", "tags": [tag]},
        ],
        "/api/v1/subnets": [],
        "/api/v1/dependencies": [],
        "/api/v1/networks": [
            {"id": "net-A", "name": "A", "tags": [tag]},  # network carries the tag itself
            {"id": "net-B", "name": "B", "tags": []},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        data = pages.get(request.url.path, [])
        return httpx.Response(
            200, json={"success": True, "data": data, "meta": {}},
            headers={"content-type": "application/json"},
        )

    async def go() -> None:
        c = _mock_client(handler)
        usage = await c.tag_usage(tag)
        by_id = {u["id"]: u for u in usage}
        assert set(by_id) == {"h1", "h2", "s1", "net-A"}
        # A network entity is its own scope.
        assert by_id["net-A"]["network_ids"] == ["net-A"]
        assert by_id["h2"]["network_ids"] == ["net-B"]
        # No network filter was applied — both net-A and net-B entities show up.
        out_of_A = [u for u in usage if u["network_ids"] != ["net-A"]]
        assert {u["id"] for u in out_of_A} == {"h2", "s1"}
        await c.aclose()

    import anyio
    anyio.run(go)
