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
            # cleanup via raw API: the scoped tool session refuses tag deletion
            # by design (org-wide destructive op under a network scope).
            all_tags = await raw.data("GET", "/api/v1/tags")
            for t in (t1, t2):
                for rec in all_tags:
                    if rec["name"] == t:
                        await raw.data("DELETE", f"/api/v1/tags/{rec['id']}")
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


async def _delete_tag_raw(raw: RawScanopy, name: str) -> None:
    for rec in await raw.data("GET", "/api/v1/tags"):
        if rec["name"] == name:
            await raw.data("DELETE", f"/api/v1/tags/{rec['id']}")


async def test_delete_tag_always_refuses_under_scope(
    env: dict[str, str], raw: RawScanopy
) -> None:
    """Scoped tag deletion refuses unconditionally — even when every VISIBLE
    use is inside the scope — because Scanopy also tags user API keys, which
    are unreadable under API-key auth: no scan can prove the blast radius
    stays in scope. (This replaced the visible-usage allow-path after two
    incomplete enumeration-based fixes.)"""
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

    try:
        # Scoped to a DIFFERENT network: refuse.
        scoped_cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK})
        scoped_client, scoped_mcp = await _session(scoped_cfg)
        try:
            async with create_connected_server_and_client_session(
                scoped_mcp._mcp_server
            ) as s:
                res = await s.call_tool("delete_tag", {"tag": tag_name, "confirm": True})
                assert res.isError
                assert "Refusing to delete tag" in res.content[0].text
        finally:
            await scoped_client.aclose()

        # Scoped to the REAL network, tag used ONLY in scope: still refuse —
        # user-API-key uses are unverifiable, so there is no provable-safe case.
        inscope_cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": real_network})
        inscope_client, inscope_mcp = await _session(inscope_cfg)
        try:
            async with create_connected_server_and_client_session(
                inscope_mcp._mcp_server
            ) as s:
                res = await s.call_tool("delete_tag", {"tag": tag_name, "confirm": True})
                assert res.isError
                text = res.content[0].text
                assert "Refusing to delete tag" in text
                assert "user API keys" in text
        finally:
            await inscope_client.aclose()

        # Tag survived both refusals.
        tags = await raw.data("GET", "/api/v1/tags")
        assert any(t["name"] == tag_name for t in tags)

        # An UNSCOPED session deletes it fine (two-phase confirm still applies).
        del_client, del_mcp = await _session(unscoped_cfg)
        try:
            async with create_connected_server_and_client_session(
                del_mcp._mcp_server
            ) as s:
                plan = await s.call_tool("delete_tag", {"tag": tag_name})
                assert not plan.isError, plan.content
                assert plan.structuredContent["mode"].startswith("plan-only")
                res = await s.call_tool("delete_tag", {"tag": tag_name, "confirm": True})
                assert not res.isError, res.content
                assert res.structuredContent["deleted"] == tag_name
        finally:
            await del_client.aclose()
    finally:
        await _delete_tag_raw(raw, tag_name)


async def test_create_tag_proceeds_but_update_refuses_under_scope(
    env: dict[str, str], raw: RawScanopy
) -> None:
    # create_tag touches no existing entity, so it proceeds under a scope.
    # update_tag and delete_tag are org-wide relabel/destroy ops whose blast
    # radius can't be verified under API-key auth, so BOTH refuse unconditionally
    # under a scope — even for a brand-new tag with zero usage (F5: the refusal
    # is not usage-conditional).
    cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": BOGUS_NETWORK})
    client, mcp = await _session(cfg)
    name = unique_name("freetag")
    try:
        async with create_connected_server_and_client_session(mcp._mcp_server) as s:
            res = await s.call_tool("create_tag", {"name": name})
            assert not res.isError, res.content
            res = await s.call_tool("update_tag", {"tag": name, "name": unique_name("re")})
            assert res.isError
            assert "Refusing to update tag" in res.content[0].text
            res = await s.call_tool("delete_tag", {"tag": name, "confirm": True})
            assert res.isError
            assert "Refusing to delete tag" in res.content[0].text
    finally:
        await client.aclose()
        await _delete_tag_raw(raw, name)


async def test_update_tag_refuses_unconditionally_under_scope(
    env: dict[str, str], raw: RawScanopy
) -> None:
    """update_tag refuses under a scope regardless of where the tag is used —
    out of scope, in scope, or nowhere visible (F5, operator decision: Option 1,
    unconditional refusal mirroring delete_tag). Unscoped, it works."""
    unscoped_cfg = Config.from_env({k: v for k, v in env.items()
                                    if k != "SCANOPY_NETWORK_ID"})
    host = await raw.create_host(unique_name("upd-oos"), ip=unique_ip())
    real_network = host["network_id"]
    tag_name = unique_name("updtag")

    setup_client, setup_mcp = await _session(unscoped_cfg)
    try:
        async with create_connected_server_and_client_session(setup_mcp._mcp_server) as s:
            await s.call_tool("create_tag", {"name": tag_name})
            await s.call_tool("set_host_tags", {"host": host["id"], "tags": [tag_name]})
    finally:
        await setup_client.aclose()

    try:
        # Scoped to a DIFFERENT network -> refuse (tag used out of scope).
        # Scoped to the host's REAL network -> STILL refuse (every visible use
        # in scope is not proof of safety; the UserApiKey blind spot remains).
        for scope in (BOGUS_NETWORK, real_network):
            scoped_cfg = Config.from_env({**env, "SCANOPY_NETWORK_ID": scope})
            scoped_client, scoped_mcp = await _session(scoped_cfg)
            try:
                async with create_connected_server_and_client_session(
                    scoped_mcp._mcp_server
                ) as s:
                    res = await s.call_tool("update_tag", {"tag": tag_name, "color": "Red"})
                    assert res.isError, f"scope={scope} should refuse"
                    assert "Refusing to update tag" in res.content[0].text
            finally:
                await scoped_client.aclose()

        # Tag unchanged after both refusals.
        tags = await raw.data("GET", "/api/v1/tags")
        assert any(t["name"] == tag_name and t.get("color") != "Red" for t in tags)

        # UNSCOPED the same rename proceeds (scope-gated, not disabled).
        renamed = f"{tag_name}-ok"
        un_client, un_mcp = await _session(unscoped_cfg)
        try:
            async with create_connected_server_and_client_session(
                un_mcp._mcp_server
            ) as s:
                res = await s.call_tool("update_tag", {"tag": tag_name, "name": renamed})
                assert not res.isError, res.content
        finally:
            await un_client.aclose()
    finally:
        for candidate in (tag_name, f"{tag_name}-ok"):
            await _delete_tag_raw(raw, candidate)
