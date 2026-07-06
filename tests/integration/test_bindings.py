"""§9 case 5 — binding create/delete plus the documented 409 conflict path.

The host (with one IP, one port, and one service) is created in a single
CreateHostRequest via the raw API; Arborist then exercises the binding
endpoints against it. Note Scanopy 0.17.3 requires network_id in the
CreateBindingRequest body, and the entity ids in the create-host response are
server-assigned (the client-sent child uuids are not preserved) — always read
them back from the response.
"""

from __future__ import annotations

import pytest

from arborist.client import ScanopyClient
from arborist.errors import ScanopyApiError

from .conftest import RawScanopy, unique_ip, unique_name

pytestmark = pytest.mark.integration


async def test_binding_lifecycle_and_conflict(
    client: ScanopyClient, raw: RawScanopy
) -> None:
    host = await raw.create_host(
        unique_name("bindhost"),
        ip=unique_ip(),
        port=8080,
        service_name=unique_name("svc"),
    )
    service = host["services"][0]
    port = host["ports"][0]
    ip = host["ip_addresses"][0]
    network_id = host["network_id"]

    created = await client.create_binding(
        {
            "service_id": service["id"],
            "network_id": network_id,
            "type": "Port",
            "port_id": port["id"],
            "ip_address_id": ip["id"],
        }
    )
    assert created["type"] == "Port"
    assert created["service_id"] == service["id"]
    assert created["port_id"] == port["id"]

    # Documented 409: an IPAddress binding is rejected while a Port binding
    # already covers that IP for the same service.
    with pytest.raises(ScanopyApiError) as excinfo:
        await client.create_binding(
            {
                "service_id": service["id"],
                "network_id": network_id,
                "type": "IPAddress",
                "ip_address_id": ip["id"],
            }
        )
    assert excinfo.value.status == 409

    await client.delete_binding(created["id"])
    remaining = {b["id"] for b in await client.list_bindings()}
    assert created["id"] not in remaining

    # With the Port binding gone the IPAddress binding is accepted — proving
    # the 409 above was the real conflict rule, not endpoint noise.
    ip_binding = await client.create_binding(
        {
            "service_id": service["id"],
            "network_id": network_id,
            "type": "IPAddress",
            "ip_address_id": ip["id"],
        }
    )
    assert ip_binding["type"] == "IPAddress"
    await client.delete_binding(ip_binding["id"])
