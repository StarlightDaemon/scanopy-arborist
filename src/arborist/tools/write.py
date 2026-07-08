"""Write-capable tool surface (§7) — registered only under ARBORIST_PROFILE=readwrite.

Every write here targets the curated/user-owned overlay from §2: host name,
description, hidden flag, tags, and bindings. Nothing in this module can touch
a discovered-layer value; host updates go through
ScanopyClient.update_host_curated, which echoes discovered fields verbatim and
never sends child arrays.

Bulk updates are two-phase per §6: called without confirm=true they return a
diff plan and change nothing.

Scope-confinement policy for org-scoped resources (tags — and the template for
anything org-scoped added later): SCANOPY_NETWORK_ID cannot be checked against
the resource itself, so confinement is decided by the operation's REACH:

- Creating an org-scoped object touches no existing entity: allowed.
- Mutating one (update_tag) changes shared labeling wherever the object is
  referenced: allowed only when every VISIBLE use (client.tag_usage) is inside
  the scope; refused on any out-of-scope or unattributable use (fail closed).
- Destroying one (delete_tag) is refused outright whenever a scope is
  configured: Scanopy 0.17.3 accepts tags on user API keys, which are
  unreadable under API-key auth (verified live — 403 "User context required"),
  so no scan can prove an org-wide deletion stays in scope. Fail closed on the
  unverifiable rather than trust an enumeration that cannot be complete —
  hand-enumerated reach lists missing quietly-taggable types is exactly how
  the two previous versions of this check went wrong.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..client import _UNSET
from ..errors import ArboristError
from ..redact import redact
from . import ToolContext
from .read import host_summary

_WRITE_SAFE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                              openWorldHint=False)
_WRITE_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                     openWorldHint=False)

# Entity types Arborist will tag/untag — deliberately NARROWER than what
# Scanopy accepts. Scanopy 0.17.3 also tags Credential, Daemon, DaemonApiKey,
# UserApiKey, and Discovery (verified empirically; see
# ScanopyClient._TAG_USAGE_SOURCES), but those are infrastructure resources
# outside Arborist's curation charter, so tag_entities/untag_entities refuse
# them client-side. Every type listed here MUST have a scope check in
# _assert_entities_in_scope — the canary test enforces both relationships.
_TAGGABLE = {"Host", "Service", "Subnet", "Network", "Dependency"}

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def _coerce_bool(value: Any, field: str = "hidden") -> bool:
    """Strict bool coercion for values that arrive untyped from a JSON tool
    call. Accepts real bools and the usual string/int spellings; rejects
    anything ambiguous so the plan and apply phases can never disagree
    (e.g. bool("false") is True, which silently inverted the plan)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
    raise ValueError(
        f"{field} must be a boolean (got {value!r}); use true/false."
    )


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
        preserved untouched. Set clear_description=true to remove the description (do not
        also pass description — that is a conflict)."""
        if clear_description and description is not None:
            raise ValueError(
                "Pass either description or clear_description=true, not both — they "
                "conflict. Use clear_description to remove the description, or description "
                "to set a new one."
            )
        record = await client.resolve_host(host)
        # Scope check BEFORE the no-op short-circuit: the short-circuit returns
        # the resolved record, and a UUID selector resolves across networks, so
        # an unchecked no-op would leak out-of-scope host metadata.
        client.assert_in_scope(record)
        desc: Any = _UNSET
        if clear_description:
            desc = None
        elif description is not None:
            desc = description

        # No-op short-circuit: a PUT that changes nothing still moves updated_at
        # (the optimistic-lock token), so skip the API call entirely when the
        # requested values already match the current record.
        effective_desc = record.get("description") if desc is _UNSET else desc
        if (
            (name is None or name == record.get("name"))
            and effective_desc == record.get("description")
            and (hidden is None or hidden == record.get("hidden"))
        ):
            return redact({"unchanged": host_summary(record)})

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
        client.assert_in_scope(record)
        tag_ids = [(await client.resolve_tag(t))["id"] for t in tags]
        if tag_ids:
            await client.set_entity_tags("Host", record["id"], tag_ids)
        else:
            # Scanopy's assign endpoint no-ops on an empty tag_ids list, so a
            # true "clear" must explicitly remove each currently-assigned tag.
            current = record.get("tags")
            if current is None:
                current = (await client.get_host(record["id"])).get("tags", [])
            for tid in current:
                await client.bulk_tag(tid, "Host", [record["id"]], remove=True)
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

        for raw in updates:
            # JSON nulls for name/hidden mean "no change"; drop them so plan and
            # apply agree. Coerce hidden to a real bool ONCE (bool("false") is
            # True, which used to invert the plan vs what apply would send).
            u = {k: v for k, v in raw.items() if not (k in ("name", "hidden") and v is None)}
            sel = str(u.get("host", ""))
            if "hidden" in u:
                try:
                    u["hidden"] = _coerce_bool(u["hidden"])
                except ValueError as exc:
                    errors.append({"host": sel, "error": str(exc)})
                    continue
            try:
                record = await client.resolve_host(sel)
            except Exception as exc:
                errors.append({"host": sel, "error": str(exc)})
                continue
            # Exclude out-of-scope hosts from the plan entirely (don't surface
            # their metadata alongside in-scope entries); apply refuses them too.
            try:
                client.assert_in_scope(record)
            except ArboristError as exc:
                errors.append({"host": sel, "error": str(exc)})
                continue
            changes = {}
            if "name" in u and u["name"] != record.get("name"):
                changes["name"] = {"from": record.get("name"), "to": u["name"]}
            if "description" in u and u["description"] != record.get("description"):
                changes["description"] = {
                    "from": record.get("description"), "to": u["description"],
                }
            if "hidden" in u and u["hidden"] != record.get("hidden"):
                changes["hidden"] = {"from": record.get("hidden"), "to": u["hidden"]}
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
        change. The tag keeps its id, so entity assignments are unaffected — but the
        label changes everywhere the tag is used, org-wide.

        Scope safety: when SCANOPY_NETWORK_ID is configured this refuses (fail-closed)
        if the tag is visibly in use on any entity outside the configured network, or
        on any entity that cannot be attributed to a network — changing a label that
        out-of-scope entities carry modifies them in effect, if not in storage."""
        # KNOWN LIMITATION (F5 / Stop Condition 11, docs/scope-confinement-audit.md):
        # this guard only sees VISIBLE usage. Scanopy 0.17.3 accepts tags on
        # UserApiKeys, which /api/v1/auth/keys will not return under API-key auth
        # (403), so a tag whose only use is on an out-of-scope UserApiKey passes
        # this check. delete_tag refuses unconditionally under scope for exactly
        # this reason; whether update_tag should do the same is a design decision
        # deliberately left to a maintainer rather than auto-patched a fourth time.
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
        if ctx.cfg.network_id:
            usage = await client.tag_usage(current["id"])
            outside = client.usage_outside_scope(usage)
            if outside:
                sample = ", ".join(
                    f"{u['entity_type']} '{u.get('name') or u['id']}'" for u in outside[:5]
                )
                raise ArboristError(
                    f"Refusing to update tag '{current['name']}': it is in use on "
                    f"{len(outside)} entit{'y' if len(outside) == 1 else 'ies'} outside "
                    f"(or not attributable to) the configured network scope "
                    f"({ctx.cfg.network_id}), e.g. {sample}. Renaming or restyling it "
                    "would change the label those out-of-scope entities carry. "
                    f"In-scope uses: {len(usage) - len(outside)}."
                )
        updated = await client.update_tag(current["id"], patch)
        return redact({"updated": {"id": updated["id"], "name": updated["name"],
                                   "color": updated.get("color")}})

    @mcp.tool(annotations=_WRITE_DESTRUCTIVE)
    async def delete_tag(tag: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a tag (by name or id). The tag disappears org-wide: every entity that
        carries it, on every network, loses that label. Requires confirm=true.

        Scope safety: when SCANOPY_NETWORK_ID is configured this ALWAYS refuses
        (fail-closed). Tag deletion is an org-wide destructive operation whose full
        blast radius cannot be verified under API-key auth — Scanopy also accepts tags
        on user API keys, and those are unreadable with an API key — so a
        network-scoped Arborist can never prove a deletion stays inside its scope.
        Delete tags from an unscoped Arborist (no SCANOPY_NETWORK_ID) or the Scanopy
        UI instead."""
        current = await client.resolve_tag(tag)
        usage = await client.tag_usage(current["id"])

        if ctx.cfg.network_id:
            outside = client.usage_outside_scope(usage)
            by_type: dict[str, int] = {}
            for u in usage:
                by_type[u["entity_type"]] = by_type.get(u["entity_type"], 0) + 1
            visible = (
                ", ".join(f"{n} {t}" for t, n in sorted(by_type.items()))
                or "none visible"
            )
            raise ArboristError(
                f"Refusing to delete tag '{current['name']}': Arborist is scoped to "
                f"network {ctx.cfg.network_id} (SCANOPY_NETWORK_ID) and tag deletion is "
                f"org-wide — the label would vanish from every entity carrying it on any "
                f"network. Visible uses: {visible} "
                f"({len(usage) - len(outside)} in scope, {len(outside)} outside or "
                "unattributable). Uses on user API keys cannot be enumerated under "
                "API-key auth at all, so even a tag with no visible out-of-scope use "
                "cannot be proven safe. Delete it from an unscoped Arborist or the "
                "Scanopy UI."
            )

        if not confirm:
            by_type = {}
            for u in usage:
                by_type[u["entity_type"]] = by_type.get(u["entity_type"], 0) + 1
            return {
                "mode": "plan-only (nothing changed)",
                "would_delete": {"id": current["id"], "name": current["name"]},
                "visible_uses": by_type,
                "note": (
                    "Deletion removes the label org-wide. Uses on user API keys are "
                    "not countable under API-key auth and are not included above."
                ),
                "next_step": "Call again with confirm=true to delete.",
            }
        await client.delete_tag(current["id"])
        return {"deleted": current["name"]}

    async def _assert_entities_in_scope(entity_type: str, entity_ids: list[str]) -> None:
        """SCANOPY_NETWORK_ID confinement for bulk tag targets. UUID lookups are
        not network-filtered server-side, so each network-scoped entity must be
        fetched and checked before we touch it."""
        if not ctx.cfg.network_id:
            return
        if entity_type == "Network":
            for eid in entity_ids:
                if eid != ctx.cfg.network_id:
                    raise ValueError(
                        f"Network {eid} is outside the configured scope "
                        f"({ctx.cfg.network_id}). Refusing to modify it."
                    )
            return
        if entity_type == "Host":
            for eid in entity_ids:
                client.assert_in_scope(await client.get_host(eid))
            return
        if entity_type == "Service":
            for eid in entity_ids:
                client.assert_in_scope(await client.get_service(eid), kind="Service")
            return
        # Subnet / Dependency: no single-GET needed — scan the scoped list.
        listing = (
            await client.list_subnets() if entity_type == "Subnet"
            else await client.list_dependencies()
        )
        in_scope = {str(e["id"]) for e in listing}
        for eid in entity_ids:
            if eid not in in_scope:
                raise ValueError(
                    f"{entity_type} {eid} is not in the configured network scope "
                    f"({ctx.cfg.network_id}). Refusing to modify it."
                )

    @mcp.tool(annotations=_WRITE_SAFE)
    async def tag_entities(
        tag: str, entity_ids: list[str], entity_type: str = "Host"
    ) -> dict[str, Any]:
        """Add one tag to many entities at once. entity_type: Host, Service, Subnet,
        Network, or Dependency. entity_ids must be ids (use list_hosts/list_services)."""
        _check_entity_type(entity_type)
        await _assert_entities_in_scope(entity_type, entity_ids)
        t = await client.resolve_tag(tag)
        result = await client.bulk_tag(t["id"], entity_type, entity_ids)
        return redact({"tag": t["name"], "result": result})

    @mcp.tool(annotations=_WRITE_SAFE)
    async def untag_entities(
        tag: str, entity_ids: list[str], entity_type: str = "Host"
    ) -> dict[str, Any]:
        """Remove one tag from many entities at once (same shape as tag_entities)."""
        _check_entity_type(entity_type)
        await _assert_entities_in_scope(entity_type, entity_ids)
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
        existing = await client.get_binding(binding_id)
        client.assert_in_scope(existing, kind="Binding")
        body = await _binding_body_for(service_id, binding_type, port_id, ip_address_id)
        updated = await client.update_binding(binding_id, body)
        return redact({"updated": updated})

    @mcp.tool(annotations=_WRITE_DESTRUCTIVE)
    async def delete_binding(binding_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a binding by id. Requires confirm=true."""
        existing = await client.get_binding(binding_id)
        client.assert_in_scope(existing, kind="Binding")
        if not confirm:
            return redact({
                "mode": "plan-only (nothing changed)",
                "would_delete": existing,
                "next_step": "Call again with confirm=true to delete.",
            })
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
        if port_id:
            raise ValueError(
                "binding_type 'IPAddress' does not take a port_id (it binds a service to "
                "an IP with no specific port). Use binding_type 'Port' to bind to a port."
            )
        return {"service_id": service_id, "type": "IPAddress",
                "ip_address_id": ip_address_id}
    raise ValueError("binding_type must be 'Port' or 'IPAddress'.")
