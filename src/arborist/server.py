"""MCP server wiring (§5.3): one tool registry, two transports.

stdio is the default and needs no HTTP hardening. The Streamable HTTP
transport only starts after Config.validate_http_transport passes (§5.5) and
is wrapped in a constant-time bearer-token gate (ARBORIST_AUTH_TOKEN) plus the
SDK's DNS-rebinding protection (ARBORIST_ALLOWED_HOSTS).
"""

from __future__ import annotations

import contextlib
import hmac
import json
import logging

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount

from . import __version__
from .client import ScanopyClient
from .config import Config, Profile, TlsPosture
from .tools import ToolContext, register_tools

logger = logging.getLogger("arborist")

INSTRUCTIONS = """\
Arborist connects you to a Scanopy instance (self-hosted network topology mapper).

Scope boundary you must respect: Scanopy's scanner owns the discovered layer
(hostnames, IPs, ports, detected services, interfaces, subnets, VLANs) — Arborist
cannot and will not modify it. The write tools (when enabled) only curate the
user-owned overlay: host display names, descriptions, hidden flags, tags, and
service bindings. Bulk operations and consolidation return a plan first and only
apply when re-called with confirm=true; show the plan to the operator before
confirming anything non-trivial.
"""


def build_mcp(cfg: Config, client: ScanopyClient, *, bind_host: str, bind_port: int) -> FastMCP:
    transport_security = _transport_security(cfg, bind_host, bind_port)
    mcp = FastMCP(
        "arborist",
        instructions=INSTRUCTIONS,
        host=bind_host,
        port=bind_port,
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
    )
    # FastMCP 1.x doesn't expose a version parameter and defaults serverInfo
    # .version to the SDK's own version; report Arborist's instead.
    mcp._mcp_server.version = __version__
    register_tools(mcp, ToolContext(cfg=cfg, client=client))
    profile = cfg.profile.value
    logger.info(
        "arborist tool surface: profile=%s consolidation=%s tools=%d",
        profile,
        cfg.enable_consolidation and cfg.profile is Profile.READWRITE,
        len(mcp._tool_manager.list_tools()),
    )
    return mcp


def _transport_security(
    cfg: Config, bind_host: str, bind_port: int
) -> TransportSecuritySettings | None:
    if not cfg.allowed_hosts:
        # §5.5 validation guarantees non-loopback binds always have
        # allowed_hosts, so this branch is loopback-only. Build the localhost
        # allowlist explicitly rather than relying on FastMCP's auto-default,
        # which only fires for the exact hosts 127.0.0.1/localhost/::1 and
        # would silently DISABLE rebinding protection for e.g. 127.0.0.2.
        hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
        origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
        if bind_host not in ("127.0.0.1", "localhost", "::1"):
            hosts.append(f"{bind_host}:*")
            origins.extend([f"http://{bind_host}:*", f"https://{bind_host}:*"])
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=origins,
        )
    hosts: list[str] = []
    origins: list[str] = []
    for entry in cfg.allowed_hosts:
        if ":" in entry:
            hosts.append(entry)
        else:
            hosts.extend([entry, f"{entry}:*"])
        bare = entry.split(":")[0]
        origins.extend([f"http://{bare}:*", f"https://{bare}:*"])
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


class BearerGate:
    """ASGI middleware enforcing the ARBORIST_AUTH_TOKEN gate secret (§5.5).

    Deliberately separate from the Scanopy API key: this token guards access
    to Arborist itself; the Scanopy key never leaves the outbound client.
    """

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        provided = b""
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                provided = value
                break
        if not hmac.compare_digest(provided, self._expected):
            body = json.dumps({"error": "unauthorized: missing or invalid bearer token"}).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self._app(scope, receive, send)


def build_http_app(mcp: FastMCP, cfg: Config):
    """Streamable HTTP ASGI app with the session-manager lifespan and auth gate."""

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    inner = Starlette(
        routes=[Mount("/", app=mcp.streamable_http_app())],
        lifespan=lifespan,
    )
    assert cfg.auth_token, "validate_http_transport must run before build_http_app"
    return BearerGate(inner, cfg.auth_token)


def run_http(mcp: FastMCP, cfg: Config, bind_host: str, bind_port: int) -> None:
    cfg.validate_http_transport(bind_host, bind_port)
    app = build_http_app(mcp, cfg)
    ssl_kwargs = {}
    if cfg.tls_posture is TlsPosture.DIRECT:
        ssl_kwargs = {"ssl_certfile": cfg.tls_cert_path, "ssl_keyfile": cfg.tls_key_path}
    logger.info(
        "arborist HTTP transport on %s:%d (posture=%s, MCP endpoint: /mcp)",
        bind_host, bind_port, cfg.tls_posture.value,
    )
    uvicorn.run(app, host=bind_host, port=bind_port, log_level="info", **ssl_kwargs)
