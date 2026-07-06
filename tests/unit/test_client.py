"""client.py — pure helpers plus _request behavior over httpx.MockTransport.

No sockets are opened anywhere: the client's real AsyncClient is closed and
swapped for one whose transport is a MockTransport.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

import arborist.client as client_mod
from arborist.client import (
    AmbiguousSelectorError,
    ScanopyClient,
    _is_uuid,
    _norm_mac,
    clamp_limit,
)
from arborist.errors import ArboristError, ScanopyApiError


class TestClampLimit:
    def test_none_becomes_default(self):
        assert clamp_limit(None) == 100

    def test_none_with_custom_default(self):
        assert clamp_limit(None, default=25) == 25

    def test_zero_never_sent(self):
        # Scanopy treats limit=0 as UNLIMITED; the clamp must never emit it.
        assert clamp_limit(0) == 1

    def test_upper_clamp(self):
        assert clamp_limit(2000) == 1000

    def test_negative_clamped_to_one(self):
        assert clamp_limit(-5) == 1

    def test_in_range_passthrough(self):
        assert clamp_limit(50) == 50


class TestPureHelpers:
    def test_ambiguous_selector_error_is_arborist_error(self):
        assert issubclass(AmbiguousSelectorError, ArboristError)

    def test_is_uuid(self):
        assert _is_uuid(str(uuid.uuid4())) is True
        assert _is_uuid("gateway") is False

    def test_norm_mac(self):
        assert _norm_mac("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"
        assert _norm_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"
        assert _norm_mac("aabb.ccdd.eeff") == "aabbccddeeff"


async def _mock_client(make_config, handler) -> ScanopyClient:
    """Real ScanopyClient with its transport swapped for a MockTransport."""
    cfg = make_config()
    client = ScanopyClient(cfg)
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=cfg.base_url,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Accept": "application/json",
        },
    )
    return client


class TestRequest:
    async def test_success_envelope_unwrapped(self, make_config):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(
                200, json={"success": True, "data": {"server_version": "0.17.3"}}
            )

        client = await _mock_client(make_config, handler)
        try:
            data = await client._request("GET", "/api/version")
        finally:
            await client.aclose()
        assert data == {"server_version": "0.17.3"}
        assert seen["path"] == "/api/version"
        assert seen["auth"].startswith("Bearer scp_u_")

    async def test_error_envelope_raises_with_code(self, make_config):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "success": False,
                    "error": "no access to entity",
                    "code": "entity_access_denied",
                    "params": {"entity_type": "Host"},
                },
            )

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError) as excinfo:
                await client._request("GET", "/api/v1/hosts/x")
        finally:
            await client.aclose()
        exc = excinfo.value
        assert exc.status == 403
        assert exc.code == "entity_access_denied"
        assert exc.params == {"entity_type": "Host"}
        assert "no access to entity" in str(exc)

    async def test_html_response_means_spa_fallback(self, make_config):
        # Scanopy's SPA answers unknown /api paths with 200 text/html.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<!doctype html><html><body>Scanopy</body></html>",
            )

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError) as excinfo:
                await client._request("GET", "/api/v1/does-not-exist")
        finally:
            await client.aclose()
        assert "does not exist" in str(excinfo.value)
        assert "text/html" in str(excinfo.value)

    async def test_raw_text_html_also_refused(self, make_config):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text="<!doctype html>"
            )

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError):
                await client._request("GET", "/api/v1/nope", raw_text=True)
        finally:
            await client.aclose()

    async def test_raw_text_returns_body(self, make_config):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "text/plain"}, text="graph TD;\n A-->B"
            )

        client = await _mock_client(make_config, handler)
        try:
            text = await client._request(
                "GET", "/api/v1/topology/t1/export/mermaid", raw_text=True
            )
        finally:
            await client.aclose()
        assert text == "graph TD;\n A-->B"

    async def test_429_retried_then_succeeds(self, make_config, monkeypatch):
        calls: list[int] = []
        waits: list[float] = []

        async def instant_sleep(seconds: float) -> None:
            waits.append(seconds)

        monkeypatch.setattr(client_mod.anyio, "sleep", instant_sleep)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={"success": False, "error": "rate limited"},
                )
            return httpx.Response(200, json={"success": True, "data": {"ok": True}})

        client = await _mock_client(make_config, handler)
        try:
            data = await client._request("GET", "/api/v1/hosts")
        finally:
            await client.aclose()
        assert data == {"ok": True}
        assert len(calls) == 2  # one retry, then success
        assert len(waits) >= 1  # backoff sleep happened (patched, so no real wait)

    async def test_429_exhausted_raises(self, make_config, monkeypatch):
        async def instant_sleep(seconds: float) -> None:
            pass

        monkeypatch.setattr(client_mod.anyio, "sleep", instant_sleep)

        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"success": False, "error": "rate limited"},
            )

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError) as excinfo:
                await client._request("GET", "/api/v1/hosts")
        finally:
            await client.aclose()
        assert excinfo.value.status == 429
        assert len(calls) == client_mod._MAX_RETRIES + 1

    async def test_401_hint_mentions_key_prefix(self, make_config):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401, json={"success": False, "error": "invalid API key"}
            )

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError) as excinfo:
                await client._request("GET", "/api/v1/networks")
        finally:
            await client.aclose()
        exc = excinfo.value
        assert exc.status == 401
        assert "scp_u_" in str(exc)  # actionable hint, not just the status code

    async def test_json_without_success_true_is_error(self, make_config):
        # A JSON body that is not the success envelope must not be trusted.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [1, 2, 3]})

        client = await _mock_client(make_config, handler)
        try:
            with pytest.raises(ScanopyApiError):
                await client._request("GET", "/api/v1/hosts")
        finally:
            await client.aclose()
