"""§9 case 4 — tag lifecycle round-trip plus the duplicate-name 409."""

from __future__ import annotations

import pytest

from arborist.client import ScanopyClient
from arborist.errors import ArboristError, ScanopyApiError

from .conftest import RawScanopy, unique_name

pytestmark = pytest.mark.integration


async def test_tag_round_trip(client: ScanopyClient, raw: RawScanopy) -> None:
    name = unique_name("tag")
    renamed = unique_name("tag-renamed")
    tag = await client.create_tag(name, color="Blue", description="integration probe")
    tag_id = tag["id"]

    try:
        assert tag["name"] == name

        resolved = await client.resolve_tag(name)
        assert resolved["id"] == tag_id

        host = await raw.create_host(unique_name("taghost"))

        # Full replace on one entity.
        await client.set_entity_tags("Host", host["id"], [tag_id])
        assert tag_id in (await client.get_host(host["id"])).get("tags", [])

        # Bulk remove, then bulk add back.
        await client.bulk_tag(tag_id, "Host", [host["id"]], remove=True)
        assert tag_id not in (await client.get_host(host["id"])).get("tags", [])
        await client.bulk_tag(tag_id, "Host", [host["id"]])
        assert tag_id in (await client.get_host(host["id"])).get("tags", [])

        # Rename via read-modify-write.
        updated = await client.update_tag(tag_id, {"name": renamed})
        assert updated["name"] == renamed
        assert (await client.resolve_tag(renamed))["id"] == tag_id
    finally:
        await client.delete_tag(tag_id)

    with pytest.raises(ArboristError):
        await client.resolve_tag(renamed)


async def test_duplicate_tag_name_conflicts_with_409(client: ScanopyClient) -> None:
    name = unique_name("dup-tag")
    tag = await client.create_tag(name)
    try:
        try:
            accidental = await client.create_tag(name)
        except ScanopyApiError as exc:
            assert exc.status == 409
            assert "unique" in exc.message.lower() or "exists" in exc.message.lower()
        else:
            await client.delete_tag(accidental["id"])
            pytest.fail("duplicate tag creation unexpectedly succeeded")
    finally:
        await client.delete_tag(tag["id"])
