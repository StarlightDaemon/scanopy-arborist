"""Write-capable tool surface (§7) — registered only under ARBORIST_PROFILE=readwrite.

Every write here targets the curated/user-owned overlay from §2: host name,
description, hidden flag, tags, and bindings. Nothing in this module can touch
a discovered-layer value; host updates go through
ScanopyClient.update_host_curated, which echoes discovered fields verbatim and
never sends child arrays.

Bulk updates are two-phase per §6: called without confirm=true they return a
diff plan and change nothing.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..redact import redact
from . import ToolContext
from .read import host_summary

_WRITE_SAFE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                              openWorldHint=False)
_WRITE_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                     openWorldHint=False)

_TAGGABLE = {"Host", "Service", "Subnet", "Network", "Dependency"}
_UNSET = object()


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    client = ctx.client

    # ------------------------------------------------------------- host metadata

    @mcp.tool(annotations=_WRITE_SAFE)
    async def update_host_metadata(
        host: str,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
        hidden: bool | None = None,
    ) -> dict[str, Any]:
        """Update a host's curated metadata: display name, description, and/or hidden
        flag. `host` may be an id, name, hostname, IP, or MAC. Only the fields you pass
        change; everything Scanopy discovered (hostname, IPs, ports, services) is
        preserved untouched. Set clear_description=true to remove the description."""
        record = await client.resolve_host(host)
        desc: Any = _UNSET
        if clear_description:
            desc = None
        elif description is not None:
            desc = description
        updated = await client.update_host_curated(
            record["id"],
            name=name,
            description=desc,
            hidden=hidden,
        )
        return redact({"updated": host_summary(updated)})

    @mcp.tool(annotations=_WRITE_SAFE)
    async def set_host_tags(host: str, tags: list[str]) -> dict[str, Any]:
        """Replace the full set of tags on a host. `tags` is a list of tag names or ids;
        pass [] to clear. To add/remove one tag across many hosts use tag_entities /
        untag_entities instead."""
        record = await client.resolve_host(host)
        tag_ids = [(await client.resolve_tag(t))["id"] for t in tags]
        await client.set_entity_tags("Host", record["id"], tag_ids)
        refreshed = await client.get_host(record["id"])
        return redact({"host": record["name"], "tag_ids": refreshed.get("tags", [])})

    @mcp.tool(annotations=_WRITE_DESTRUCTIVE)
    async def bulk_update_hosts(
        updates: list[dict[str, Any]], confirm: bool = False
    ) -> dict[str, Any]:
        """Apply metadata updates to several hosts at once. Each update is
        {"host": <id|name|ip|mac>, "name"?: str, "description"?: str, "hidden"?: bool}.

        Two-phase: with confirm=false (default) this returns a diff plan of exactly what
        would change and modifies NOTHING. Review the plan (with the operator when in
        doubt), then call again with confirm=true to apply."""
        plan: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        resolved: list[tuple[dict[str, Any], dict[str, Any]]] = []

        for u in updates:
            sel = str(u.get("host", ""))
            try:
                record = await client.resolve_host(sel)
            except Exception as exc:
                errors.append({"host": sel, "error": str(exc)})
                continue
            changes = {}
            if "name" in u and u["name"] != record.get("name"):
                changes["name"] = {"from": record.get("name"), "to": u["name"]}
            if "description" in u and u["description"] != record.get("description"):
                changes["description"] = {
                    "from": record.get("description"), "to": u["description"],
                }
            if "hidden" in u and bool(u["hidden"]) != record.get("hidden"):
                changes["hidden"] = {"from": record.get("hidden"), "to": bool(u["hidden"])}
            plan.append({"host_id": record["id"], "host": record.get("name"),
                         "changes": changes or "no-op"})
            if changes:
                resolved.append((record, u))

        if not confirm:
            return redact({
                "mode": "plan-only (nothing changed)",
                "plan": plan,
                "errors": errors,
                "to_apply": len(resolved),
                "next_step": "Call bulk_update_hosts again with confirm=true to apply.",
            })

        applied, failed = [], list(errors)
        for record, u in resolved:
            try:
                await client.update_host_curated(
                    record["id"],
                    name=u.get("name"),
                    description=u["description"] if "description" in u else _UNSET,
                    hidden=u.get("hidden"),
                )
                applied.append(record.get("name"))
            except Exception as exc:
                failed.append({"host": record.get("name"), "error": str(exc)})
        return redact({"mode": "applied", "applied": applied, "failed": failed})

    # -------------------------------------------------------------------- tags

    @mcp.tool(annotations=_WRITE_SAFE)
    async def create_tag(
        name: str,
        color: str = "Gray",
        description: str | None = None,
        is_application: bool = False,
    ) -> dict[str, Any]:
        """Create a tag. Colors: Pink, Rose, Red, Amber, Orange, Green, Emerald, Teal,
        Cyan, Blue, Indigo, Purple, Fuchsia, Violet, Sky, Gray, Lime, Yellow.
        is_application=true makes it an application tag (groups services into an
        application in Scanopy's Applications view). Requires an Admin-level API key."""
        tag = await client.create_tag(
            name, color=color, description=description, is_application=is_application
        )
        return redact({"created": {"id": tag["id"], "name": tag["name"],
                                   "color": tag.get("color")}})

    @mcp.tool(annotations=_WRITE_SAFE)
    async def update_tag(
        tag: str,
        name: str | None = None,
        color: str | None = None,
        description: str | None = None,
        is_application: bool | None = None,
    ) -> dict[str, Any]:
        """Rename or restyle an existing tag (by name or id). Only the fields you pass
        change."""
        current = await client.resolve_tag(tag)
        patch: dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if color is not None:
            patch["color"] = color
        if description is not None:
            patch["description"] = description
        if is_application is not None:
            patch["is_application"] = is_application
        if not patch:
            return {"unchanged": current["name"]}
        updated = await client.update_tag(current["id"], patch)
        return redact({"updated": {"id": updated["id"], "name": updated["name"],
                                   "color": updated.get("color")}})

    @mcp.tool(annotations=_WRITE_DESTRUCTIVE)
    async def delete_tag(tag: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a tag (by name or id). It is removed from every entity that carries it.
        Requires confirm=true."""
        current = await client.resolve_tag(tag)
        if not confirm:
            return {
                "mode": "plan-only (nothing changed)",
                "would_delete": {"id": current["id"], "name": current["name"]},
                "next_step": "Call again with confirm=true to delete.",
            }
        await client.delete_tag(current["id"])
        return {"deleted": current["name"]}

    @mcp.tool(annotations=_WRITE_SAFE)
    async def tag_entities(
        tag: str, entity_ids: list[str], entity_type: str = "Host"
    ) -> dict[str, Any]:
        """Add one tag to many entities at once. entity_type: Host, Service, Subnet,
        Network, or Dependency. entity_ids must be ids (use list_hosts/list_services)."""
        _check_entity_type(entity_type)
        t = await client.resolve_tag(tag)
        result = await client.bulk_tag(t["id"], entity_type, entity_ids)
        return redact({"tag": t["name"], "result": result})

    @mcp.tool(annotations=_WRITE_SAFE)
    async def untag_entities(
        tag: str, entity_ids: list[str], entity_type: str = "Host"
    ) -> dict[str, Any]:
        """Remove one tag from many entities at once (same shape as tag_entities)."""
        _check_entity_type(entity_type)
        t = await client.resolve_tag(tag)
        result = await client.bulk_tag(t["id"], entity_type, entity_ids, remove=True)
        return redact({"tag": t["name"], "result": result})

    # ---------------------------------------------------------------- bindings

    async def _binding_body_for(
        service_id: str, binding_type: str, port_id: str | None, ip_address_id: str | None
    ) -> dict[str, Any]:
        # Scanopy requires network_id in binding bodies; derive it from the
        # owning service, which also lets the network-scope confinement apply.
        service = await client.get_service(service_id)
        if ctx.cfg.network_id and str(service.get("network_id")) != ctx.cfg.network_id:
            raise ValueError(
                f"Service {service_id} belongs to network {service.get('network_id')}, but "
                f"Arborist is scoped to network {ctx.cfg.network_id} (SCANOPY_NETWORK_ID). "
                "Refusing to modify its bindings."
            )
        body = _binding_body(service_id, binding_type, port_id, ip_address_id)
        body["network_id"] = service["network_id"]
        return body

    @mcp.tool(annotations=_WRITE_SAFE)
    async def create_binding(
        service_id: str,
        binding_type: str,
        port_id: str | None = None,
        ip_address_id: str | None = None,
    ) -> dict[str, Any]:
        """Bind a service to network resources on its host. binding_type 'Port' needs
        port_id (ip_address_id optional; null = listens on all IPs — note this supersedes
        any per-IP bindings for that port). binding_type 'IPAddress' needs ip_address_id
        (service present at an IP without a specific port, e.g. a gateway). A binding
        whose type clashes with an existing one on the same IP/port is rejected by
        Scanopy with a 409 explaining the conflict (exact duplicates are not rejected)."""
        body = await _binding_body_for(service_id, binding_type, port_id, ip_address_id)
        created = await client.create_binding(body)
        return redact({"created": created})

    @mcp.tool(annotations=_WRITE_SAFE)
    async def update_binding(
        binding_id: str,
        service_id: str,
        binding_type: str,
        port_id: str | None = None,
        ip_address_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing binding (same fields and 409 conflict rules as
        create_binding)."""
        body = await _binding_body_for(service_id, binding_type, port_id, ip_address_id)
        updated = await client.update_binding(binding_id, body)
        return redact({"updated": updated})

    @mcp.tool(annotations=_WRITE_DESTRUCTIVE)
    async def delete_binding(binding_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a binding by id. Requires confirm=true."""
        if not confirm:
            return {
                "mode": "plan-only (nothing changed)",
                "would_delete": binding_id,
                "next_step": "Call again with confirm=true to delete.",
            }
        await client.delete_binding(binding_id)
        return {"deleted": binding_id}


def _check_entity_type(entity_type: str) -> None:
    if entity_type not in _TAGGABLE:
        raise ValueError(
            f"entity_type must be one of {sorted(_TAGGABLE)}; got {entity_type!r}."
        )


def _binding_body(
    service_id: str, binding_type: str, port_id: str | None, ip_address_id: str | None
) -> dict[str, Any]:
    if binding_type == "Port":
        if not port_id:
            raise ValueError("binding_type 'Port' requires port_id.")
        return {"service_id": service_id, "type": "Port", "port_id": port_id,
                "ip_address_id": ip_address_id}
    if binding_type == "IPAddress":
        if not ip_address_id:
            raise ValueError("binding_type 'IPAddress' requires ip_address_id.")
        return {"service_id": service_id, "type": "IPAddress",
                "ip_address_id": ip_address_id}
    raise ValueError("binding_type must be 'Port' or 'IPAddress'.")
