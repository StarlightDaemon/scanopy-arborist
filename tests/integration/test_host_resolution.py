"""§9 case 2 — host-ID-404 re-resolution after a consolidation retires a record."""

from __future__ import annotations

import pytest

from arborist.client import ScanopyClient
from arborist.errors import HostNotFoundError, ScanopyApiError

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration


async def test_resolve_host_positive_by_id_name_ip_mac(
    client: ScanopyClient, raw: RawScanopy
) -> None:
    name = unique_name("resolve")
    ip = unique_ip()
    mac = "aa:bb:cc:00:99:42"
    host = await raw.create_host(name, ip=ip, mac=mac)

    by_id = await client.resolve_host(host["id"])
    by_name = await client.resolve_host(name)
    by_ip = await client.resolve_host(ip)
    # MAC matching is separator/case-insensitive; the server stores uppercase.
    by_mac = await client.resolve_host("AA-BB-CC-00-99-42")

    assert by_id["id"] == by_name["id"] == by_ip["id"] == by_mac["id"] == host["id"]


async def test_retired_host_id_gets_reresolution_guidance(
    client: ScanopyClient, raw: RawScanopy
) -> None:
    dest = await raw.create_host(unique_name("consol-dest"), ip=unique_ip())
    other_name = unique_name("consol-other")
    other = await raw.create_host(other_name)

    merged = await client.consolidate_hosts(dest["id"], other["id"])
    assert merged["id"] == dest["id"]

    # The raw endpoint answers a plain 404 for the retired id...
    with pytest.raises(ScanopyApiError) as excinfo:
        await client.get_host(other["id"])
    assert excinfo.value.status == 404

    # ...but resolve_host turns it into consolidation guidance, not a dead end.
    with pytest.raises(HostNotFoundError) as notfound:
        await client.resolve_host(other["id"])
    assert "consolidation" in str(notfound.value)
    assert notfound.value.status == 404

    # Resolving by the retired host's NAME: on 0.17.3 the destination keeps its
    # own name, so this raises with candidates; if a future version merges
    # names, the survivor must come back instead.
    try:
        survivor = await client.resolve_host(other_name)
    except HostNotFoundError as exc:
        assert isinstance(exc.candidates, list)
        assert "consolidation" in str(exc)
    else:
        assert survivor["id"] == dest["id"]

    # The survivor is still resolvable normally.
    resolved_dest = await client.resolve_host(dest["id"])
    assert resolved_dest["id"] == dest["id"]
