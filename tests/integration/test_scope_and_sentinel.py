"""Live regression tests for the adversarial-review findings.

Two behaviors, both through the real FastMCP tool layer against the live
disposable instance:
1. SCANOPY_NETWORK_ID confinement now covers every write tool — a client
   scoped to a bogus network must be refused on consolidation, tag writes,
   and binding deletion even when it addresses hosts by raw UUID.
2. Rename-only / hidden-only host updates work (the _UNSET sentinel mismatch
   used to crash them before any bytes were sent)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration

BOGUS_NETWORK = str(uuid.uuid4())


async def _call(session: Any, tool: str, args: dict[str, Any]) -> Any:
    return await session.call_tool(tool, args)


async def test_out_of_scope_writes_refused(
    env: dict[str, str], raw: RawScanopy
) -> None:
    host_a = await raw.create_host(unique_name("scopeA"), ip=unique_ip())
    host_b = await raw.create_host(
        unique_name("scopeB"), ip=unique_ip(), port=8082, service_name=unique_name("svc")
    )

    # A readwrite+consolidation server scoped to a network that owns nothing.
    # (Session opened inside the test: anyio cancel scopes cannot cross the
    # pytest fixture setup/teardown task boundary.)
    scoped_env = {**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK}
    cfg = Config.from_env(scoped_env)
    client = ScanopyClient(cfg)
    try:
        mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
        async with create_connected_server_and_client_session(
            mcp._mcp_server
        ) as session:
            await _assert_refusals(session, raw, host_a, host_b)
    finally:
        await client.aclose()


async def _assert_refusals(
    session: Any, raw: RawScanopy, host_a: dict[str, Any], host_b: dict[str, Any]
) -> None:
    # consolidate_hosts: refused before even the preview, by raw UUID.
    res = await _call(session, "consolidate_hosts", {
        "destination": host_a["id"], "source": host_b["id"], "confirm": True,
    })
    assert res.isError
    assert "scoped to network" in res.content[0].text
    still_there = await raw.data("GET", f"/api/v1/hosts/{host_b['id']}")
    assert still_there["id"] == host_b["id"], "host must not be deleted"

    # set_host_tags by raw UUID.
    res = await _call(session, "set_host_tags", {"host": host_a["id"], "tags": []})
    assert res.isError
    assert "scoped to network" in res.content[0].text

    # tag_entities / untag_entities by raw UUID.
    for tool in ("tag_entities", "untag_entities"):
        res = await _call(session, tool, {
            "tag": "stage0-tag", "entity_ids": [host_a["id"]], "entity_type": "Host",
        })
        assert res.isError
        assert "scoped to network" in res.content[0].text

    # delete_binding on an out-of-scope binding (create it in-scope first).
    service = host_b["services"][0]
    port = host_b["ports"][0]
    binding = await raw.data("POST", "/api/v1/bindings", json={
        "service_id": service["id"],
        "network_id": host_b["network_id"],
        "type": "Port",
        "port_id": port["id"],
        "ip_address_id": None,
    })
    res = await _call(session, "delete_binding", {
        "binding_id": binding["id"], "confirm": True,
    })
    assert res.isError
    assert "scoped to network" in res.content[0].text
    # update_host_metadata (control: was already guarded).
    res = await _call(session, "update_host_metadata", {
        "host": host_a["id"], "name": "should-never-apply",
    })
    assert res.isError


async def test_rename_only_and_hidden_only_updates(
    cfg: Config, raw: RawScanopy
) -> None:
    host = await raw.create_host(unique_name("sentinel"), ip=unique_ip())
    client = ScanopyClient(cfg)
    try:
        mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
        async with create_connected_server_and_client_session(
            mcp._mcp_server
        ) as session:
            new_name = unique_name("sentinel-renamed")
            res = await _call(session, "update_host_metadata", {
                "host": host["id"], "name": new_name,
            })
            assert not res.isError, res.content
            assert res.structuredContent["updated"]["name"] == new_name

            res = await _call(session, "update_host_metadata", {
                "host": host["id"], "hidden": True,
            })
            assert not res.isError, res.content
            updated = res.structuredContent["updated"]
            assert updated["hidden"] is True
            assert updated["name"] == new_name, "hidden-only update must not touch name"

            # bulk apply row without a description key
            res = await _call(session, "bulk_update_hosts", {
                "updates": [{"host": host["id"], "hidden": False, "name": None}],
                "confirm": True,
            })
            assert not res.isError, res.content
            assert res.structuredContent["failed"] == []
    finally:
        await client.aclose()
