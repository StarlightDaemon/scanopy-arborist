"""Live regression tests for the fix pass — findings #1, #4, #5, #8 and the
SC8 delete_tag fail-closed confinement, all driven through the real MCP tool
layer against the disposable Scanopy instance."""

from __future__ import annotations

import uuid

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration

BOGUS_NETWORK = str(uuid.uuid4())


async def _session(cfg: Config):
    client = ScanopyClient(cfg)
    mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
    return client, mcp


# ---------------------------------------------------- #1 set_host_tags([]) clears


async def test_set_host_tags_empty_actually_clears(cfg: Config, raw: RawScanopy) -> None:
    host = await raw.create_host(unique_name("cleartags"), ip=unique_ip())
    client, mcp = await _session(cfg)
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            t1 = unique_name("t")
            t2 = unique_name("t")
            await s.call_tool("create_tag", {"name": t1})
            await s.call_tool("create_tag", {"name": t2})
            res = await s.call_tool("set_host_tags", {"host": host["id"], "tags": [t1, t2]})
            assert len(res.structuredContent["tag_ids"]) == 2

            # The bug: empty list no-oped. It must now truly clear.
            res = await s.call_tool("set_host_tags", {"host": host["id"], "tags": []})
            assert res.structuredContent["tag_ids"] == []
            fresh = await raw.data("GET", f"/api/v1/hosts/{host['id']}")
            assert fresh["tags"] == []
            # cleanup tags
            for t in (t1, t2):
                await s.call_tool("delete_tag", {"tag": t, "confirm": True})
    finally:
        await client.aclose()


# ---------------------------------------- #4/#5 update_host_metadata conflict/no-op


async def test_clear_description_conflict_rejected(cfg: Config, raw: RawScanopy) -> None:
    host = await raw.create_host(unique_name("conflict"), ip=unique_ip())
    client, mcp = await _session(cfg)
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            res = await s.call_tool("update_host_metadata", {
                "host": host["id"], "description": "x", "clear_description": True,
            })
            assert res.isError
            assert "not both" in res.content[0].text
    finally:
        await client.aclose()


async def test_noop_update_does_not_touch_updated_at(cfg: Config, raw: RawScanopy) -> None:
    host = await raw.create_host(unique_name("noop"), ip=unique_ip())
    before = (await raw.data("GET", f"/api/v1/hosts/{host['id']}"))["updated_at"]
    client, mcp = await _session(cfg)
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            # Same name it already has -> no effective change -> no PUT.
            res = await s.call_tool("update_host_metadata", {
                "host": host["id"], "name": host["name"],
            })
            assert "unchanged" in res.structuredContent
            after = (await raw.data("GET", f"/api/v1/hosts/{host['id']}"))["updated_at"]
            assert after == before, "no-op update must not move updated_at"
    finally:
        await client.aclose()


# --------------------------------------------- #3 bulk hidden plan/apply agree


async def test_bulk_hidden_string_plan_matches_apply(cfg: Config, raw: RawScanopy) -> None:
    host = await raw.create_host(unique_name("bulkhidden"), ip=unique_ip())
    assert host["hidden"] is False
    client, mcp = await _session(cfg)
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            # "true" (string) must be understood as hidden=True in BOTH phases,
            # not bool("true")-vs-raw-string disagreement.
            plan = await s.call_tool("bulk_update_hosts", {
                "updates": [{"host": host["id"], "hidden": "true"}],
            })
            changes = plan.structuredContent["plan"][0]["changes"]
            assert changes["hidden"] == {"from": False, "to": True}

            applied = await s.call_tool("bulk_update_hosts", {
                "updates": [{"host": host["id"], "hidden": "true"}], "confirm": True,
            })
            assert applied.structuredContent["failed"] == []
            assert host["name"] in applied.structuredContent["applied"]
            fresh = await raw.data("GET", f"/api/v1/hosts/{host['id']}")
            assert fresh["hidden"] is True

            # An un-coercible value is a clean per-row error, not a crash/422.
            bad = await s.call_tool("bulk_update_hosts", {
                "updates": [{"host": host["id"], "hidden": "maybe"}],
            })
            assert bad.structuredContent["errors"]
            assert "boolean" in bad.structuredContent["errors"][0]["error"]
    finally:
        await client.aclose()


# ------------------------------------------- #8 bulk plan excludes out-of-scope


async def test_bulk_plan_excludes_out_of_scope(env: dict[str, str], raw: RawScanopy) -> None:
    host = await raw.create_host(unique_name("oos"), ip=unique_ip())
    cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK})
    client, mcp = await _session(cfg)
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            res = await s.call_tool("bulk_update_hosts", {
                "updates": [{"host": host["id"], "name": "should-not-appear"}],
            })
            sc = res.structuredContent
            # The out-of-scope host must NOT appear in the plan; it's an error row.
            assert sc["plan"] == []
            assert sc["errors"]
            assert "scoped to network" in sc["errors"][0]["error"]
            # And its current name/description are not disclosed in the plan.
            assert "should-not-appear" not in str(sc["plan"])
    finally:
        await client.aclose()


# ------------------------------------- SC8: delete_tag fail-closed confinement


async def test_delete_tag_fails_closed_on_out_of_scope_use(
    env: dict[str, str], raw: RawScanopy
) -> None:
    # Create a tag and apply it to an in-network host, using an UNSCOPED session.
    unscoped_cfg = Config.from_env({k: v for k, v in env.items()
                                    if k != "SCANOPY_NETWORK_ID"})
    host = await raw.create_host(unique_name("tagged"), ip=unique_ip())
    real_network = host["network_id"]
    tag_name = unique_name("scopetag")

    setup_client, setup_mcp = await _session(unscoped_cfg)
    try:
        async with create_connected_server_and_client_session(setup_mcp._mcp_server) as s:
            await s.call_tool("create_tag", {"name": tag_name})
            await s.call_tool("set_host_tags", {"host": host["id"], "tags": [tag_name]})
    finally:
        await setup_client.aclose()

    # A session scoped to a DIFFERENT network must refuse to delete it (the tag
    # is applied to an out-of-scope host).
    scoped_cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK})
    scoped_client, scoped_mcp = await _session(scoped_cfg)
    try:
        async with create_connected_server_and_client_session(scoped_mcp._mcp_server) as s:
            res = await s.call_tool("delete_tag", {"tag": tag_name, "confirm": True})
            assert res.isError
            assert "Refusing to delete tag" in res.content[0].text
            assert "outside the configured network scope" in res.content[0].text
        # Tag still exists.
        tags = await raw.data("GET", "/api/v1/tags")
        assert any(t["name"] == tag_name for t in tags)
    finally:
        await scoped_client.aclose()

    # A session scoped to the REAL network deletes it fine (only in-scope uses).
    inscope_cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": real_network})
    inscope_client, inscope_mcp = await _session(inscope_cfg)
    try:
        async with create_connected_server_and_client_session(inscope_mcp._mcp_server) as s:
            res = await s.call_tool("delete_tag", {"tag": tag_name, "confirm": True})
            assert not res.isError, res.content
            assert res.structuredContent["deleted"] == tag_name
    finally:
        await inscope_client.aclose()


async def test_create_and_update_tag_ignore_scope(
    env: dict[str, str], raw: RawScanopy
) -> None:
    # create_tag / update_tag don't touch entity associations, so they proceed
    # regardless of scope (per the documented policy).
    cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK})
    client, mcp = await _session(cfg)
    name = unique_name("freetag")
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            res = await s.call_tool("create_tag", {"name": name})
            assert not res.isError, res.content
            newname = unique_name("renamed")
            res = await s.call_tool("update_tag", {"tag": name, "name": newname})
            assert not res.isError, res.content
            # delete has no out-of-scope uses (fresh tag on nothing) -> allowed.
            res = await s.call_tool("delete_tag", {"tag": newname, "confirm": True})
            assert not res.isError, res.content
    finally:
        await client.aclose()
