"""Punch-list item 8: a live-shaped credential must never appear in tool output.

Drives the real tool layer (in-memory MCP session) against the live instance
and scans every byte of every result — text content and structuredContent —
for the actual API key in use and for anything shaped like a Scanopy key."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import build_mcp

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration

# scp_u_ / scp_d_ followed by a plausible token body (Scanopy keys are 32+).
KEY_SHAPE = re.compile(r"scp_[ud]_[A-Za-z0-9]{16,}")


def _dump(result: Any) -> str:
    parts = [c.text for c in result.content if hasattr(c, "text")]
    if result.structuredContent is not None:
        parts.append(json.dumps(result.structuredContent, default=str))
    return "\n".join(parts)


async def test_no_live_secret_in_any_tool_output(
    cfg: Config, raw: RawScanopy
) -> None:
    host = await raw.create_host(
        unique_name("redact"), ip=unique_ip(), port=8083,
        service_name=unique_name("svc"),
    )
    client = ScanopyClient(cfg)
    secret = cfg.api_key
    try:
        mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
        async with create_connected_server_and_client_session(
            mcp._mcp_server
        ) as session:
            calls: list[tuple[str, dict[str, Any]]] = [
                # Read profile — every tool.
                ("get_instance_info", {}),
                ("list_networks", {}),
                ("list_hosts", {}),
                ("list_hosts", {"search": "redact"}),
                ("get_host", {"host": host["id"]}),
                ("list_services", {}),
                ("list_subnets", {}),
                ("list_ports", {}),
                ("list_host_addresses", {}),
                ("list_snmp_interfaces", {}),
                ("list_dependencies", {}),
                ("list_tags", {}),
                ("list_bindings", {}),
                ("get_topology", {}),
                ("export_topology_mermaid", {}),
                # Credential-adjacent write tools.
                ("update_host_metadata", {"host": host["id"], "description": "redaction probe"}),
                ("set_host_tags", {"host": host["id"], "tags": []}),
                # Error path: errors must not echo credentials either.
                ("get_host", {"host": "00000000-0000-0000-0000-000000000000"}),
            ]
            for tool, args in calls:
                result = await session.call_tool(tool, args)
                text = _dump(result)
                assert secret not in text, f"{tool} leaked the live API key"
                match = KEY_SHAPE.search(text)
                assert match is None, f"{tool} output contains key-shaped value {match.group()[:12]}..."
    finally:
        await client.aclose()
