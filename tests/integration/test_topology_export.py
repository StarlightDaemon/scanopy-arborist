"""§9 case 7 — Mermaid export of the live topology."""

from __future__ import annotations

import pytest

from arborist.client import ScanopyClient

pytestmark = pytest.mark.integration


async def test_export_topology_mermaid_returns_flowchart(client: ScanopyClient) -> None:
    topologies = await client.list_topologies()
    live = [t for t in topologies if not t.get("snapshot_id")]
    assert live, "the test instance has no live topology"

    text = await client.export_topology_mermaid(live[0]["id"], view="L3Logical")
    assert isinstance(text, str)
    assert "flowchart" in text
