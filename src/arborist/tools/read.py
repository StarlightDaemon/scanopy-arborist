"""Read-only tool surface (§7) — strictly GET requests against Scanopy.

Responses are projected down to what an LLM needs: full host records from
Scanopy embed every port/service/interface child and would drown the context
window, so list tools return compact summaries and get_host returns a trimmed
detail view. Everything passes through redact() before leaving (§5.8).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .. import __version__
from ..compat import supported_range
from ..config import Profile
from ..redact import redact
from . import ToolContext

_READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

# Keep list responses bounded even if a caller asks for more.
MAX_LIST_LIMIT = 500


def host_summary(h: dict[str, Any]) -> dict[str, Any]:
    services = h.get("services", [])
    return {
        "id": h.get("id"),
        "name": h.get("name"),
        "hostname": h.get("hostname"),
        "description": h.get("description"),
        "hidden": h.get("hidden"),
        "source": (h.get("source") or {}).get("type"),
        "network_id": h.get("network_id"),
        "ip_addresses": [ip.get("ip_address") for ip in h.get("ip_addresses", [])],
        "mac_addresses": sorted(
            {ip["mac_address"] for ip in h.get("ip_addresses", []) if ip.get("mac_address")}
        ),
        "services": [
            {"id": s.get("id"), "name": s.get("name"), "definition": s.get("service_definition")}
            for s in services
        ],
        "open_port_count": len(h.get("ports", [])),
        "tag_ids": h.get("tags", []),
    }


def host_detail(h: dict[str, Any]) -> dict[str, Any]:
    detail = host_summary(h)
    detail["ports"] = [
        {"id": p.get("id"), "number": p.get("number"), "protocol": p.get("protocol"),
         "type": p.get("type")}
        for p in h.get("ports", [])
    ]
    detail["ip_address_records"] = [
        {"id": ip.get("id"), "ip_address": ip.get("ip_address"),
         "mac_address": ip.get("mac_address"), "name": ip.get("name"),
         "subnet_id": ip.get("subnet_id")}
        for ip in h.get("ip_addresses", [])
    ]
    detail["services"] = [
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "definition": s.get("service_definition"),
            "bindings": s.get("bindings", []),
            "tag_ids": s.get("tags", []),
        }
        for s in h.get("services", [])
    ]
    detail["snmp_interface_count"] = len(h.get("interfaces", []))
    detail["management_url"] = h.get("management_url")
    detail["created_at"] = h.get("created_at")
    detail["updated_at"] = h.get("updated_at")
    return detail


def service_summary(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": s.get("id"),
        "name": s.get("name"),
        "definition": s.get("service_definition"),
        "host_id": s.get("host_id"),
        "network_id": s.get("network_id"),
        "source": (s.get("source") or {}).get("type"),
        "binding_count": len(s.get("bindings", [])),
        "tag_ids": s.get("tags", []),
    }


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    client = ctx.client
    cfg = ctx.cfg

    def _limit(limit: int) -> int:
        return max(1, min(limit, MAX_LIST_LIMIT))

    @mcp.tool(annotations=_READ)
    async def get_instance_info() -> dict[str, Any]:
        """Connection, version, and capability overview: the Scanopy server version, this
        Arborist's profile (readonly/readwrite), whether consolidation is enabled, and any
        network scoping in effect. Call this first when orienting."""
        info = await client.version_info()
        return redact({
            "arborist_version": __version__,
            "scanopy": info,
            "supported_scanopy_range": supported_range(),
            "profile": cfg.profile.value,
            "consolidation_enabled": cfg.enable_consolidation,
            "scoped_to_network_id": cfg.network_id,
            "writable_fields": (
                ["host.name", "host.description", "host.hidden", "tags", "bindings"]
                if cfg.profile is Profile.READWRITE
                else []
            ),
        })

    @mcp.tool(annotations=_READ)
    async def list_networks() -> list[dict[str, Any]]:
        """List the networks visible to this API key (id, name, tags)."""
        nets = await client.list_networks()
        return redact([
            {"id": n.get("id"), "name": n.get("name"), "tag_ids": n.get("tags", [])}
            for n in nets
        ])

    @mcp.tool(annotations=_READ)
    async def list_hosts(
        network_id: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List hosts as compact summaries (name, IPs, services, hidden flag, tags).
        `tag` filters by tag name or id; `search` is a case-insensitive substring match on
        name/hostname/IP. Use get_host for full detail on one host."""
        tag_ids = None
        if tag:
            tag_ids = [(await client.resolve_tag(tag))["id"]]
        if search:
            # Substring search must see every host, not one server-side page —
            # scan all pages, filter, then paginate the filtered result.
            needle = search.lower()

            def hit(h: dict[str, Any]) -> bool:
                if needle in str(h.get("name", "")).lower():
                    return True
                if needle in (h.get("hostname") or "").lower():
                    return True
                return any(
                    needle in (ip.get("ip_address") or "") for ip in h.get("ip_addresses", [])
                )

            matched = [
                h for h in await client.list_all_hosts(network_id=network_id, tag_ids=tag_ids)
                if hit(h)
            ]
            page = matched[offset:offset + _limit(limit)]
            return redact({
                "count": len(page),
                "total_matches": len(matched),
                "offset": offset,
                "hosts": [host_summary(h) for h in page],
            })
        hosts = await client.list_hosts(
            network_id=network_id, tag_ids=tag_ids, limit=_limit(limit), offset=offset
        )
        return redact({
            "count": len(hosts),
            "offset": offset,
            "hosts": [host_summary(h) for h in hosts],
        })

    @mcp.tool(annotations=_READ)
    async def get_host(host: str) -> dict[str, Any]:
        """Full detail for one host. `host` may be a host id, name, hostname, IP, or MAC
        address; retired ids (after consolidation) are re-resolved when possible."""
        record = await client.resolve_host(host)
        return redact(host_detail(record))

    @mcp.tool(annotations=_READ)
    async def list_services(
        network_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """List detected services (name, definition from Scanopy's catalog, owning host)."""
        services = await client.list_services(
            network_id=network_id, limit=_limit(limit), offset=offset
        )
        return redact({
            "count": len(services),
            "offset": offset,
            "services": [service_summary(s) for s in services],
        })

    @mcp.tool(annotations=_READ)
    async def list_subnets(network_id: str | None = None) -> list[dict[str, Any]]:
        """List subnets (CIDR, name, type). Includes Scanopy's synthetic Internet/Remote
        subnets used to model external services."""
        subnets = await client.list_subnets(network_id=network_id)
        return redact([
            {
                "id": s.get("id"), "name": s.get("name"), "cidr": s.get("cidr"),
                "type": s.get("subnet_type"), "description": s.get("description"),
                "source": (s.get("source") or {}).get("type"), "tag_ids": s.get("tags", []),
            }
            for s in subnets
        ])

    @mcp.tool(annotations=_READ)
    async def list_ports(
        network_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> dict[str, Any]:
        """List discovered open ports across hosts (number, protocol, host id)."""
        ports = await client.list_ports(network_id=network_id, limit=_limit(limit), offset=offset)
        return redact({
            "count": len(ports),
            "offset": offset,
            "ports": [
                {"id": p.get("id"), "number": p.get("number"), "protocol": p.get("protocol"),
                 "type": p.get("type"), "host_id": p.get("host_id")}
                for p in ports
            ],
        })

    @mcp.tool(annotations=_READ)
    async def list_host_addresses(
        network_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> dict[str, Any]:
        """List IP address records (Scanopy's per-host interface entries): IP, MAC,
        owning host, subnet."""
        ips = await client.list_ip_addresses(
            network_id=network_id, limit=_limit(limit), offset=offset
        )
        return redact({
            "count": len(ips),
            "offset": offset,
            "addresses": [
                {"id": i.get("id"), "ip_address": i.get("ip_address"),
                 "mac_address": i.get("mac_address"), "name": i.get("name"),
                 "host_id": i.get("host_id"), "subnet_id": i.get("subnet_id")}
                for i in ips
            ],
        })

    @mcp.tool(annotations=_READ)
    async def list_snmp_interfaces(
        network_id: str | None = None, limit: int = 200, offset: int = 0
    ) -> dict[str, Any]:
        """List SNMP ifTable interface entries (switch/router ports with LLDP/CDP
        neighbor info), where SNMP discovery is in use."""
        entries = await client.list_snmp_interfaces(
            network_id=network_id, limit=_limit(limit), offset=offset
        )
        return redact({
            "count": len(entries),
            "offset": offset,
            "interfaces": [
                {
                    "id": e.get("id"), "host_id": e.get("host_id"),
                    "if_index": e.get("if_index"), "if_name": e.get("if_name"),
                    "if_descr": e.get("if_descr"), "if_alias": e.get("if_alias"),
                    "oper_status": e.get("oper_status"), "speed_bps": e.get("speed_bps"),
                    "mac_address": e.get("mac_address"),
                    "lldp_sys_name": e.get("lldp_sys_name"),
                    "neighbor": e.get("neighbor"),
                }
                for e in entries
            ],
        })

    @mcp.tool(annotations=_READ)
    async def list_dependencies(network_id: str | None = None) -> list[dict[str, Any]]:
        """List service dependency edges (name, type, member service/binding ids)."""
        deps = await client.list_dependencies(network_id=network_id)
        return redact([
            {
                "id": d.get("id"), "name": d.get("name"),
                "description": d.get("description"), "type": d.get("dependency_type"),
                "members": d.get("members", []),
                "source": (d.get("source") or {}).get("type"), "tag_ids": d.get("tags", []),
            }
            for d in deps
        ])

    @mcp.tool(annotations=_READ)
    async def list_tags() -> list[dict[str, Any]]:
        """List all tags (id, name, color, is_application). Tag ids appearing on hosts,
        services, and subnets resolve here."""
        tags = await client.list_tags()
        return redact([
            {
                "id": t.get("id"), "name": t.get("name"), "color": t.get("color"),
                "description": t.get("description"),
                "is_application": t.get("is_application"),
            }
            for t in tags
        ])

    @mcp.tool(annotations=_READ)
    async def list_bindings(
        service: str | None = None, network_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List service bindings (how a service attaches to ports/IPs). Optionally filter
        by service id."""
        bindings = await client.list_bindings(network_id=network_id)
        if service:
            bindings = [b for b in bindings if b.get("service_id") == service]
        return redact(bindings)

    @mcp.tool(annotations=_READ)
    async def get_topology(network_id: str | None = None) -> dict[str, Any]:
        """Get the topology record for a network (id + configured grouping/view options).
        The topology id is what export_topology_mermaid needs."""
        topo = await _live_topology(network_id)
        return redact({
            "id": topo.get("id"),
            "network_id": topo.get("network_id"),
            "views": ["L2Physical", "L3Logical", "Workloads", "Application"],
            "options": topo.get("options"),
        })

    @mcp.tool(annotations=_READ)
    async def export_topology_mermaid(
        network_id: str | None = None, view: str = "L3Logical"
    ) -> str:
        """Export a network's topology as a Mermaid flowchart (.mmd text). `view` is one of
        L2Physical, L3Logical, Workloads, Application. (Scanopy renders SVG client-side
        only, so Mermaid is the machine-readable export.)"""
        topo = await _live_topology(network_id)
        return await client.export_topology_mermaid(topo["id"], view=view)

    async def _live_topology(network_id: str | None) -> dict[str, Any]:
        topologies = await client.list_topologies(network_id=network_id)
        live = [t for t in topologies if not t.get("snapshot_id")]
        if not live:
            raise ValueError(
                "No topology found. If you have multiple networks, pass network_id "
                "(see list_networks)."
            )
        if len(live) > 1 and not network_id and not cfg.network_id:
            names = ", ".join(str(t.get("network_id")) for t in live)
            raise ValueError(
                f"Multiple networks have topologies ({names}); pass network_id to pick one."
            )
        return live[0]
