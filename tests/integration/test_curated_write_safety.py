"""§9 case 3 — update_host_curated must never disturb the discovered layer.

Runs against the pre-existing discovered host 'arborist-stage0-renamed' and
restores its description afterwards; children/tags/hostname are asserted
byte-identical across the write.
"""

from __future__ import annotations

from typing import Any

import pytest

from arborist.client import ScanopyClient

pytestmark = pytest.mark.integration

DISCOVERED_HOST_NAME = "arborist-stage0-renamed"
CHILD_KEYS = ("ip_addresses", "ports", "services")


def _child_ids(host: dict[str, Any], key: str) -> list[str]:
    return sorted(str(c["id"]) for c in host.get(key) or [])


async def test_curated_description_update_preserves_discovered_layer(
    client: ScanopyClient,
) -> None:
    before = await client.resolve_host(DISCOVERED_HOST_NAME)
    host_id = before["id"]
    original_description = before.get("description")

    try:
        await client.update_host_curated(host_id, description="integration-test-touch")
        after = await client.get_host(host_id)

        assert after.get("description") == "integration-test-touch"
        assert after.get("description") != original_description

        # Discovered layer untouched: same children (ids and counts), same
        # hostname, same tags.
        for key in CHILD_KEYS:
            assert _child_ids(after, key) == _child_ids(before, key), key
            assert len(after.get(key) or []) == len(before.get(key) or []), key
        assert after.get("hostname") == before.get("hostname")
        assert sorted(after.get("tags", [])) == sorted(before.get("tags", []))
        assert after.get("name") == before.get("name")
        assert after.get("hidden") == before.get("hidden")
    finally:
        await client.update_host_curated(host_id, description=original_description)

    restored = await client.get_host(host_id)
    assert restored.get("description") == original_description
    for key in CHILD_KEYS:
        assert _child_ids(restored, key) == _child_ids(before, key), key
