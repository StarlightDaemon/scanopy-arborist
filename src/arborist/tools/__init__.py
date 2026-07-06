"""Tool registration — the §7 profile boundary lives here.

Profile gating is structural: tools that are not part of the active profile
are never registered with the MCP server at all, so a readonly Arborist has
no write tools for a client to even attempt.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from ..client import ScanopyClient
from ..config import Config, Profile


@dataclass
class ToolContext:
    cfg: Config
    client: ScanopyClient


def register_tools(mcp: FastMCP, ctx: ToolContext) -> None:
    from . import consolidate, read, write

    read.register(mcp, ctx)
    if ctx.cfg.profile is Profile.READWRITE:
        write.register(mcp, ctx)
        if ctx.cfg.enable_consolidation:
            consolidate.register(mcp, ctx)
