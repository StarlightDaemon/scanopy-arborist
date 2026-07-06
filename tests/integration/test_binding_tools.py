"""Tool-level binding coverage: the MCP tools must inject network_id themselves.

The client-level tests in test_bindings.py pass a raw body including
network_id; this file exercises the actual create_binding/delete_binding tools
through an in-process MCP session, which is the path a Claude client uses (and
the path that broke when network_id was omitted)."""

from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration


async def test_binding_tools_roundtrip(cfg: Config, raw: RawScanopy) -> None:
    host = await raw.create_host(
        unique_name("bindtool"),
        ip=unique_ip(),
        port=8081,
        service_name=unique_name("svc"),
    )
    service = host["services"][0]
    port = host["ports"][0]

    tool_client = ScanopyClient(cfg)
    try:
        mcp = build_mcp(cfg, tool_client, bind_host="127.0.0.1", bind_port=60074)
        async with create_connected_server_and_client_session(
            mcp._mcp_server
        ) as session:
            created = await session.call_tool(
                "create_binding",
                {
                    "service_id": service["id"],
                    "binding_type": "Port",
                    "port_id": port["id"],
                },
            )
            assert not created.isError, created.content
            binding = created.structuredContent["created"]
            assert binding["type"] == "Port"
            assert binding["network_id"] == host["network_id"]

            deleted = await session.call_tool(
                "delete_binding", {"binding_id": binding["id"], "confirm": True}
            )
            assert not deleted.isError, deleted.content
            assert deleted.structuredContent["deleted"] == binding["id"]
    finally:
        await tool_client.aclose()
