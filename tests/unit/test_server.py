"""server.py — BearerGate as pure ASGI, and structural profile gating (§7)."""

from __future__ import annotations

import json

from arborist.client import ScanopyClient
from arborist.config import Config
from arborist.server import BearerGate, _transport_security, build_mcp

TOKEN = "unit-test-token-0123456789"


# --------------------------------------------------------------- BearerGate


class RecordingApp:
    """Minimal inner ASGI app that records whether it was reached."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        if scope["type"] == "http":
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            await send({"type": "http.response.body", "body": b"inner ok"})


async def _drive(gate, headers: list[tuple[bytes, bytes]], scope_type: str = "http"):
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": scope_type, "headers": headers}
    await gate(scope, receive, send)
    return sent


class TestBearerGate:
    async def test_correct_token_passes_through(self):
        inner = RecordingApp()
        gate = BearerGate(inner, TOKEN)
        sent = await _drive(gate, [(b"authorization", f"Bearer {TOKEN}".encode())])
        assert inner.called
        assert sent[0]["status"] == 200
        assert sent[1]["body"] == b"inner ok"

    async def test_wrong_token_gets_401(self):
        inner = RecordingApp()
        gate = BearerGate(inner, TOKEN)
        sent = await _drive(gate, [(b"authorization", b"Bearer wrong-token-000000")])
        assert not inner.called
        assert sent[0]["status"] == 401
        body = json.loads(sent[1]["body"])
        assert "unauthorized" in body["error"]

    async def test_missing_header_gets_401(self):
        inner = RecordingApp()
        gate = BearerGate(inner, TOKEN)
        sent = await _drive(gate, [])
        assert not inner.called
        assert sent[0]["status"] == 401

    async def test_token_without_bearer_scheme_gets_401(self):
        inner = RecordingApp()
        gate = BearerGate(inner, TOKEN)
        sent = await _drive(gate, [(b"authorization", TOKEN.encode())])
        assert not inner.called
        assert sent[0]["status"] == 401

    async def test_non_http_scope_bypasses_gate(self):
        # Lifespan traffic must reach the inner app or the server never starts.
        inner = RecordingApp()
        gate = BearerGate(inner, TOKEN)
        await _drive(gate, [], scope_type="lifespan")
        assert inner.called


# ----------------------------------------------------------- profile gating

READ_TOOLS = {"get_instance_info", "list_hosts", "get_host", "list_tags", "get_topology"}
WRITE_TOOLS = {
    "update_host_metadata",
    "set_host_tags",
    "bulk_update_hosts",
    "create_tag",
    "update_tag",
    "delete_tag",
    "tag_entities",
    "untag_entities",
    "create_binding",
    "update_binding",
    "delete_binding",
}
CONSOLIDATE_TOOL = "consolidate_hosts"


async def _tool_names(cfg: Config) -> set[str]:
    client = ScanopyClient(cfg)
    try:
        mcp = build_mcp(cfg, client, bind_host="127.0.0.1", bind_port=60074)
        return {t.name for t in mcp._tool_manager.list_tools()}
    finally:
        await client.aclose()


class TestProfileGating:
    async def test_readonly_registers_no_write_tools(self, make_config):
        names = await _tool_names(make_config())
        assert READ_TOOLS <= names
        assert not (WRITE_TOOLS & names)
        assert CONSOLIDATE_TOOL not in names

    async def test_readwrite_registers_write_tools(self, make_config):
        names = await _tool_names(make_config(ARBORIST_PROFILE="readwrite"))
        assert READ_TOOLS <= names
        assert WRITE_TOOLS <= names
        # Consolidation stays off without its own flag.
        assert CONSOLIDATE_TOOL not in names

    async def test_consolidation_flag_adds_consolidate_hosts(self, make_config):
        names = await _tool_names(
            make_config(
                ARBORIST_PROFILE="readwrite", ARBORIST_ENABLE_CONSOLIDATION="true"
            )
        )
        assert WRITE_TOOLS <= names
        assert CONSOLIDATE_TOOL in names


# ---------------------------------------------------- transport security map


class TestTransportSecuritySettings:
    def test_no_allowed_hosts_uses_sdk_defaults(self, make_config):
        assert _transport_security(make_config(), "127.0.0.1", 60074) is None

    def test_allowed_hosts_expand_ports_and_origins(self, make_config):
        cfg = make_config(ARBORIST_ALLOWED_HOSTS="arborist.lan:60074,plain")
        settings = _transport_security(cfg, "0.0.0.0", 60074)
        assert settings is not None
        assert settings.enable_dns_rebinding_protection is True
        assert "arborist.lan:60074" in settings.allowed_hosts
        # A port-less entry covers both the bare host and any port.
        assert "plain" in settings.allowed_hosts
        assert "plain:*" in settings.allowed_hosts
        assert "http://arborist.lan:*" in settings.allowed_origins
        assert "https://plain:*" in settings.allowed_origins
