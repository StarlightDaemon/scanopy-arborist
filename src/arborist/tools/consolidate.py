"""Host consolidation — behind ARBORIST_ENABLE_CONSOLIDATION (§7).

Consolidation never edits discovered values; it reassigns which host record
owns discovered interfaces/ports/services, then Scanopy deletes the emptied
source record. Sanctioned curation, but a bigger blast radius than a rename —
hence the separate opt-in flag and the mandatory two-phase confirm."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..errors import ScanopyApiError
from ..redact import redact
from . import ToolContext
from .read import host_summary

_CONSOLIDATE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False,
                               openWorldHint=False)


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    client = ctx.client

    @mcp.tool(annotations=_CONSOLIDATE)
    async def consolidate_hosts(
        destination: str, source: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Merge duplicate host records: every interface, port, and service of `source`
        moves onto `destination`, then the source record is deleted. Use when one physical
        machine was discovered as two hosts (e.g. seen from two VLANs by different
        daemons).

        Two-phase: with confirm=false (default) this returns a merge preview and changes
        NOTHING. Constraints enforced by Scanopy: a host cannot be merged into itself,
        both hosts must be on the same network, and a host that has a daemon attached
        cannot be merged away (merge the other host into it instead)."""
        dest = await client.resolve_host(destination)
        src = await client.resolve_host(source)
        # Scope confinement before even the preview: UUID resolution is not
        # network-filtered, and this is the one tool that deletes a record.
        client.assert_in_scope(dest)
        client.assert_in_scope(src)

        preview = {
            "destination": host_summary(dest),
            "source": host_summary(src),
            "will_move": {
                "ip_addresses": len(src.get("ip_addresses", [])),
                "ports": len(src.get("ports", [])),
                "services": len(src.get("services", [])),
            },
            "note": (
                "Duplicate interfaces/ports on the destination are deduplicated; bindings "
                "are remapped onto the surviving records. The source host record "
                f"'{src.get('name')}' ({src['id']}) will be DELETED."
            ),
        }

        if dest["id"] == src["id"]:
            return redact({
                "mode": "refused",
                "reason": "destination and source resolve to the same host.",
                "preview": preview,
            })

        if not confirm:
            return redact({
                "mode": "plan-only (nothing changed)",
                "preview": preview,
                "next_step": "Call again with confirm=true to merge.",
            })

        try:
            merged = await client.consolidate_hosts(dest["id"], src["id"])
        except ScanopyApiError as exc:
            # Surface Scanopy's validation (same-network, daemon-attached, ...) verbatim.
            return redact({"mode": "rejected-by-scanopy", "error": exc.actionable()})

        return redact({
            "mode": "merged",
            "retired_host_id": src["id"],
            "merged": host_summary(merged),
        })
