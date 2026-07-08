"""Unit tests for the scope-confinement audit fixes (2026-07-07):

- tag_usage() scans every enumerable taggable type and reports list-shaped
  network attribution (the SC8 fix, third iteration — empirically derived).
- usage_outside_scope() classification rules, including fail-closed on
  org-scoped records with no network attribution.
- delete_tag ALWAYS refuses under a network scope (the UserApiKey blind spot
  makes the blast radius unverifiable, so there is no allow path to test).
- update_tag ALWAYS refuses under a network scope too (F5 / operator Option 1),
  regardless of what tag_usage() returns — the refusal is unconditional, not
  usage-conditional, and does not consult tag_usage() at all.
- update_host_metadata's no-op short-circuit cannot leak out-of-scope hosts.

Live counterparts: tests/integration/test_fix_pass_live.py and the canary in
tests/integration/test_tag_scope_canary.py.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import anyio
import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

NET_A = "11111111-1111-1111-1111-111111111111"
NET_B = "22222222-2222-2222-2222-222222222222"
TAG = "aaaaaaaa-0000-0000-0000-00000000000a"
HOST_B = "bbbbbbbb-0000-0000-0000-00000000000b"


def make_config(**overrides: str) -> Config:
    env = {
        "SCANOPY_BASE_URL": "http://scanopy.test:60072",
        "SCANOPY_API_KEY": "scp_u_unit-test-key",
        "ARBORIST_PROFILE": "readwrite",
        **overrides,
    }
    return Config.from_env(env)


def _client_with_pages(
    pages: dict[str, Any], cfg: Config, seen_paths: set[str] | None = None,
    puts: list[tuple[str, Any]] | None = None,
) -> ScanopyClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if seen_paths is not None and request.method == "GET":
            seen_paths.add(path)
        if request.method in ("PUT", "POST", "DELETE") and puts is not None:
            puts.append((f"{request.method} {path}", request.content))
        data = pages.get(path)
        if data is None:
            return httpx.Response(
                404,
                json={"success": False, "error": f"not found: {path}", "meta": {}},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200, json={"success": True, "data": data, "meta": {}},
            headers={"content-type": "application/json"},
        )

    c = ScanopyClient(cfg)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=cfg.base_url
    )
    return c


# ----------------------------------------------------------- tag_usage sources


def test_tag_usage_scans_every_enumerable_taggable_type() -> None:
    """The two prior SC8 escapes were both 'the scan missed a type'. Lock the
    scanned path set to the full enumerable-taggable list."""
    seen: set[str] = set()
    pages = {path: [] for path, _ in ScanopyClient._TAG_USAGE_SOURCES.values()}

    async def go() -> None:
        c = _client_with_pages(pages, make_config(), seen_paths=seen)
        assert await c.tag_usage(TAG) == []
        await c.aclose()

    anyio.run(go)
    expected = {path for path, _ in ScanopyClient._TAG_USAGE_SOURCES.values()}
    assert expected == {
        "/api/v1/hosts", "/api/v1/services", "/api/v1/subnets", "/api/v1/networks",
        "/api/v1/dependencies", "/api/v1/daemons", "/api/v1/auth/daemon",
        "/api/v1/discovery", "/api/v1/credentials",
    }
    assert expected <= seen, f"tag_usage skipped paths: {expected - seen}"


def test_tag_usage_attribution_shapes() -> None:
    pages = {path: [] for path, _ in ScanopyClient._TAG_USAGE_SOURCES.values()}
    pages["/api/v1/hosts"] = [
        {"id": "h1", "name": "in", "network_id": NET_A, "tags": [TAG]},
        {"id": "h2", "name": "untagged", "network_id": NET_A, "tags": []},
    ]
    pages["/api/v1/networks"] = [{"id": NET_A, "name": "A", "tags": [TAG]}]
    pages["/api/v1/daemons"] = [
        {"id": "d1", "name": "daemon", "network_id": NET_B, "tags": [TAG]},
    ]
    pages["/api/v1/credentials"] = [
        {"id": "c1", "name": "cred-unassigned", "assigned_network_ids": [], "tags": [TAG]},
        {"id": "c2", "name": "cred-a", "assigned_network_ids": [NET_A], "tags": [TAG]},
    ]

    async def go() -> None:
        c = _client_with_pages(pages, make_config())
        usage = {u["id"]: u for u in await c.tag_usage(TAG)}
        assert set(usage) == {"h1", NET_A, "d1", "c1", "c2"}
        assert usage["h1"]["network_ids"] == [NET_A]
        # A network entity is its own attribution.
        assert usage[NET_A]["network_ids"] == [NET_A]
        assert usage["d1"]["network_ids"] == [NET_B]
        # Credentials: list-shaped, possibly empty; flagged org_scoped.
        assert usage["c1"]["network_ids"] == [] and usage["c1"]["org_scoped"]
        assert usage["c2"]["network_ids"] == [NET_A]
        await c.aclose()

    anyio.run(go)


# ------------------------------------------------------- usage_outside_scope


@pytest.mark.parametrize(
    "network_ids,outside",
    [
        ([NET_A], False),          # exactly the scope: inside
        ([NET_B], True),           # different network: outside
        ([NET_A, NET_B], True),    # spans beyond the scope: outside
        ([], True),                # no attribution at all: fail closed
    ],
)
def test_usage_outside_scope_classification(network_ids: list[str], outside: bool) -> None:
    async def go() -> None:
        c = _client_with_pages({}, make_config(SCANOPY_NETWORK_ID=NET_A))
        rec = {"entity_type": "Credential", "id": "x", "name": "x",
               "network_ids": network_ids, "org_scoped": True}
        assert bool(c.usage_outside_scope([rec])) is outside
        await c.aclose()

    anyio.run(go)


def test_usage_outside_scope_empty_without_scope() -> None:
    async def go() -> None:
        c = _client_with_pages({}, make_config())  # no SCANOPY_NETWORK_ID
        rec = {"entity_type": "Host", "id": "x", "name": "x",
               "network_ids": [NET_B], "org_scoped": False}
        assert c.usage_outside_scope([rec]) == []
        await c.aclose()

    anyio.run(go)


# ------------------------------------------------------------ tool behaviors


def _tool_session(pages: dict[str, Any], cfg: Config,
                  puts: list[tuple[str, Any]] | None = None):
    client = _client_with_pages(pages, cfg, puts=puts)
    mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
    return client, mcp


def _base_pages() -> dict[str, Any]:
    pages: dict[str, Any] = {path: [] for path, _ in ScanopyClient._TAG_USAGE_SOURCES.values()}
    pages["/api/v1/tags"] = [
        {"id": TAG, "name": "mytag", "color": "Gray", "description": None,
         "is_application": False},
    ]
    pages[f"/api/v1/tags/{TAG}"] = pages["/api/v1/tags"][0]
    return pages


def test_delete_tag_always_refuses_under_scope() -> None:
    """Even a tag whose every VISIBLE use is in scope must be refused: uses on
    user API keys are invisible under API-key auth, so in-scope-looking is not
    provably in-scope."""
    pages = _base_pages()
    pages["/api/v1/hosts"] = [
        {"id": "h1", "name": "in-scope", "network_id": NET_A, "tags": [TAG]},
    ]
    puts: list[tuple[str, Any]] = []

    async def go() -> None:
        client, mcp = _tool_session(pages, make_config(SCANOPY_NETWORK_ID=NET_A), puts=puts)
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                res = await s.call_tool("delete_tag", {"tag": "mytag", "confirm": True})
                assert res.isError
                text = res.content[0].text
                assert "Refusing to delete tag" in text
                assert "org-wide" in text
                assert "user API keys" in text.lower() or "user API keys" in text
        finally:
            await client.aclose()

    anyio.run(go)
    assert puts == [], f"refused delete must make no write calls, saw {puts}"


def test_delete_tag_unscoped_still_works() -> None:
    pages = _base_pages()
    puts: list[tuple[str, Any]] = []

    async def go() -> None:
        client, mcp = _tool_session(pages, make_config(), puts=puts)
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                plan = await s.call_tool("delete_tag", {"tag": "mytag"})
                assert not plan.isError, plan.content
                assert plan.structuredContent["mode"].startswith("plan-only")
                res = await s.call_tool("delete_tag", {"tag": "mytag", "confirm": True})
                assert not res.isError, res.content
                assert res.structuredContent["deleted"] == "mytag"
        finally:
            await client.aclose()

    anyio.run(go)
    assert [p for p in puts if p[0].startswith("DELETE")] == [
        (f"DELETE /api/v1/tags/{TAG}", b""),
    ]


# ---------------------------------- update_tag: unconditional scoped refusal (F5)
#
# Operator decision (F5 handoff): update_tag refuses UNCONDITIONALLY whenever a
# network scope is configured, exactly like delete_tag — NOT a usage-conditional
# check. tag_usage()'s UserApiKey blind spot means "looks safe" can never be
# proven, so the refusal must not depend on what tag_usage() returns. These two
# cases prove the refusal is unconditional, not merely triggered on out-of-scope
# usage: one with ZERO visible usage (the exact shape the original escape
# exploited) and one with only IN-SCOPE visible usage. Both must refuse.


def test_update_tag_refuses_under_scope_with_zero_visible_usage() -> None:
    """Case 1 (§2): a tag whose tag_usage() is [] — the shape the UserApiKey
    escape exploited — must STILL be refused under a scope. If this proceeds,
    the refusal has a usage-conditional path in it that shouldn't exist."""
    pages = _base_pages()  # no entity pages carry TAG -> tag_usage() == []
    puts: list[tuple[str, Any]] = []
    usage_scans: list[str] = []

    def track(pages_, cfg):
        # Wrap so we can assert tag_usage() is never consulted for the decision.
        client = _client_with_pages(pages_, cfg, puts=puts)
        orig = client.tag_usage

        async def spy(tag_id):  # pragma: no cover - should not be called
            usage_scans.append(tag_id)
            return await orig(tag_id)

        client.tag_usage = spy  # type: ignore[method-assign]
        mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
        return client, mcp

    async def go() -> None:
        client, mcp = track(pages, make_config(SCANOPY_NETWORK_ID=NET_A))
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                res = await s.call_tool("update_tag", {"tag": "mytag", "name": "renamed"})
                assert res.isError
                assert "Refusing to update tag" in res.content[0].text
        finally:
            await client.aclose()

    anyio.run(go)
    assert puts == [], f"refused update must make no write calls, saw {puts}"
    assert usage_scans == [], (
        "update_tag consulted tag_usage() in the scoped refusal path — the refusal "
        "must be unconditional, not usage-conditional (F5 regression)"
    )


def test_update_tag_refuses_under_scope_even_with_only_in_scope_use() -> None:
    """Case 2 (§2): a tag whose only visible use is IN scope must STILL be
    refused. Proves the check doesn't special-case 'looks safe' situations."""
    pages = _base_pages()
    pages["/api/v1/hosts"] = [
        {"id": "h1", "name": "in-scope", "network_id": NET_A, "tags": [TAG]},
    ]
    puts: list[tuple[str, Any]] = []

    async def go() -> None:
        client, mcp = _tool_session(pages, make_config(SCANOPY_NETWORK_ID=NET_A), puts=puts)
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                res = await s.call_tool("update_tag", {"tag": "mytag", "color": "Red"})
                assert res.isError
                assert "Refusing to update tag" in res.content[0].text
        finally:
            await client.aclose()

    anyio.run(go)
    assert puts == [], f"refused update must make no write calls, saw {puts}"


def test_update_tag_proceeds_when_unscoped() -> None:
    """Without a scope the tool still works — the refusal is scope-gated, not a
    blanket disable."""
    pages = _base_pages()
    pages["/api/v1/hosts"] = [
        {"id": "h1", "name": "anywhere", "network_id": NET_B, "tags": [TAG]},
    ]
    puts: list[tuple[str, Any]] = []

    async def go() -> None:
        client, mcp = _tool_session(pages, make_config(), puts=puts)  # no scope
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                res = await s.call_tool("update_tag", {"tag": "mytag", "name": "renamed"})
                assert not res.isError, res.content
        finally:
            await client.aclose()

    anyio.run(go)
    assert [p for p, _ in puts] == [f"PUT /api/v1/tags/{TAG}"]
    put_paths = [p for p, _ in puts]
    assert put_paths == [f"PUT /api/v1/tags/{TAG}"]


def test_update_host_metadata_noop_cannot_leak_out_of_scope_host() -> None:
    """A no-op update on an out-of-scope host (selected by UUID) must refuse,
    not return the host's metadata via the 'unchanged' short-circuit."""
    pages: dict[str, Any] = {
        f"/api/v1/hosts/{HOST_B}": {
            "id": HOST_B, "name": "secret-host", "hidden": False,
            "network_id": NET_B, "tags": [], "description": "confidential",
        },
    }

    async def go() -> None:
        client, mcp = _tool_session(pages, make_config(SCANOPY_NETWORK_ID=NET_A))
        try:
            async with create_connected_server_and_client_session(mcp._mcp_server) as s:
                res = await s.call_tool(
                    "update_host_metadata", {"host": HOST_B, "name": "secret-host"}
                )
                assert res.isError
                text = res.content[0].text
                assert "scoped to network" in text
                assert "confidential" not in text
        finally:
            await client.aclose()

    anyio.run(go)
