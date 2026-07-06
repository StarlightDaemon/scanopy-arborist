"""§9 case 6 — profile gating smoke: the tool surface is structural, not advisory."""

from __future__ import annotations

import pytest

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

pytestmark = pytest.mark.integration

WRITE_TOOLS = {
    "update_host_metadata",
    "set_host_tags",
    "bulk_update_hosts",
    "create_tag",
    "update_tag",
    "delete_tag",
    "tag_entities",
    "untag_entities",
    "create_binding",
    "update_binding",
    "delete_binding",
}
CONSOLIDATE_TOOL = "consolidate_hosts"


def _tool_names(env: dict[str, str]) -> set[str]:
    cfg = Config.from_env(env)
    client = ScanopyClient(cfg)
    mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
    return {t.name for t in mcp._tool_manager.list_tools()}


async def test_readonly_profile_registers_no_write_tools(env: dict[str, str]) -> None:
    readonly_env = {**env, "ARBORIST_PROFILE": "readonly"}
    readonly_env.pop("ARBORIST_ENABLE_CONSOLIDATION", None)
    names = _tool_names(readonly_env)
    assert names, "readonly profile should still expose read tools"
    assert {"list_hosts", "get_host"} <= names
    assert not names & WRITE_TOOLS
    assert CONSOLIDATE_TOOL not in names


async def test_readwrite_without_consolidation_flag(env: dict[str, str]) -> None:
    rw_env = {**env, "ARBORIST_PROFILE": "readwrite"}
    rw_env.pop("ARBORIST_ENABLE_CONSOLIDATION", None)
    names = _tool_names(rw_env)
    assert WRITE_TOOLS <= names
    assert CONSOLIDATE_TOOL not in names


async def test_readwrite_with_consolidation_flag(env: dict[str, str]) -> None:
    names = _tool_names(
        {**env, "ARBORIST_PROFILE": "readwrite", "ARBORIST_ENABLE_CONSOLIDATION": "true"}
    )
    assert WRITE_TOOLS <= names
    assert CONSOLIDATE_TOOL in names
