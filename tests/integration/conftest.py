"""Shared fixtures for the live-instance integration suite (§9).

SAFETY RAIL — read before pointing this suite anywhere: these tests create,
mutate, consolidate, and delete records, so they are for a DISPOSABLE Scanopy
instance only. The whole suite skips unless the SCANOPY_BASE_URL host is
loopback (localhost / 127.0.0.1) or the operator explicitly sets
ARBORIST_TEST_ALLOW_REMOTE=1.

Credentials come from the environment (SCANOPY_BASE_URL / SCANOPY_API_KEY /
SCANOPY_NETWORK_ID). When SCANOPY_API_KEY is unset, the suite falls back to
reading ARBORIST_TEST_ENV_FILE (a KEY=value file kept outside the repo so the
disposable key is never committed). The file is only ever read.
"""

from __future__ import annotations

import os
import random
import uuid
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

import anyio
import httpx
import pytest

from arborist.client import ScanopyClient
from arborist.config import Config

DEFAULT_BASE_URL = "http://localhost:60072"

_DEFAULT_TEST_ENV_FILE = (
    "/private/tmp/claude-501/-Users-dante-Citadel-scanopy-arborist/"
    "07b1f56f-5b2a-4267-a4da-eff476b9748f/scratchpad/scanopy-test/.test-env"
)

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Everything this suite creates is named with this prefix so stray leftovers
# from an aborted run are recognizable (and safe to delete by hand).
TEST_PREFIX = "arborist-itest"


# --------------------------------------------------------------- settings/rail


def _read_env_file() -> dict[str, str]:
    path = Path(os.environ.get("ARBORIST_TEST_ENV_FILE", _DEFAULT_TEST_ENV_FILE))
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _settings() -> dict[str, str]:
    file_env = _read_env_file()
    return {
        "base_url": (
            os.environ.get("SCANOPY_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
        ),
        "api_key": os.environ.get("SCANOPY_API_KEY", "").strip()
        or file_env.get("SCANOPY_API_KEY", ""),
        "network_id": os.environ.get("SCANOPY_NETWORK_ID", "").strip()
        or file_env.get("SCANOPY_NETWORK_ID", ""),
    }


def _skip_reason() -> str | None:
    s = _settings()
    host = (urlsplit(s["base_url"]).hostname or "").lower()
    if host not in _LOOPBACK_HOSTS and os.environ.get("ARBORIST_TEST_ALLOW_REMOTE") != "1":
        return (
            f"integration tests are destructive and only run against a disposable local "
            f"instance; SCANOPY_BASE_URL host {host!r} is not loopback. Set "
            "ARBORIST_TEST_ALLOW_REMOTE=1 only if you are certain the target is disposable."
        )
    if not s["api_key"]:
        return "SCANOPY_API_KEY is not set and no test env file was found."
    return None


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    reason = _skip_reason()
    if reason is None:
        return
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(marker)


# -------------------------------------------------------------------- fixtures


@pytest.fixture(scope="session")
def settings() -> dict[str, str]:
    return _settings()


@pytest.fixture(scope="session")
def live(settings: dict[str, str]) -> None:
    """Reachability gate: skip (not error) when the disposable instance is down."""
    try:
        resp = httpx.get(f"{settings['base_url']}/api/version", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"Scanopy test instance unreachable at {settings['base_url']}: {exc}")


@pytest.fixture()
def env(settings: dict[str, str], live: None) -> dict[str, str]:
    """Env mapping for Config.from_env, wired to the live disposable instance."""
    e = {
        "SCANOPY_BASE_URL": settings["base_url"],
        "SCANOPY_API_KEY": settings["api_key"],
        "ARBORIST_PROFILE": "readwrite",
        "ARBORIST_ENABLE_CONSOLIDATION": "true",
    }
    if settings["network_id"]:
        e["SCANOPY_NETWORK_ID"] = settings["network_id"]
    return e


@pytest.fixture()
def cfg(env: dict[str, str]) -> Config:
    return Config.from_env(env)


@pytest.fixture()
async def client(cfg: Config) -> AsyncIterator[ScanopyClient]:
    c = ScanopyClient(cfg)
    try:
        yield c
    finally:
        await c.aclose()


class RawScanopy:
    """Direct API access for test setup/teardown that Arborist itself refuses
    to do by design (host creation/deletion is scanner/operator territory,
    not curation). Tracks created hosts and deletes them at teardown."""

    def __init__(self, http: httpx.AsyncClient, network_id: str | None) -> None:
        self.http = http
        self.network_id = network_id
        self.created_host_ids: list[str] = []

    async def data(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        # Retry 429s honoring Retry-After: the live limiter is shared across
        # the whole suite (test_rate_limit_live deliberately exhausts it), and
        # the raw fixture must not be brittle to that.
        for _ in range(5):
            resp = await self.http.request(method, path, params=params, json=json)
            if resp.status_code != 429:
                break
            wait = resp.headers.get("Retry-After")
            await anyio.sleep(float(wait) if wait and wait.replace(".", "").isdigit() else 1.0)
        body = resp.json()
        assert body.get("success") is True, (
            f"raw {method} {path} failed: HTTP {resp.status_code} {body}"
        )
        return body.get("data")

    async def pick_subnet(self) -> dict[str, Any]:
        """A subnet that accepts arbitrary test IPs — prefer the 0.0.0.0/0
        'Remote Network' system subnet so 10.99.x.y addresses always fit."""
        subnets = await self.data(
            "GET",
            "/api/v1/subnets",
            params={"limit": 200, "offset": 0, "network_id": self.network_id},
        )
        assert subnets, "the test instance has no subnets"
        for s in subnets:
            if s.get("subnet_type") == "Remote":
                return s
        return subnets[0]

    async def create_host(
        self,
        name: str,
        *,
        ip: str | None = None,
        mac: str | None = None,
        subnet_id: str | None = None,
        port: int | None = None,
        service_name: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "network_id": self.network_id,
            "hidden": False,
            "tags": [],
        }
        if ip is not None:
            if subnet_id is None:
                subnet_id = (await self.pick_subnet())["id"]
            entry: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "subnet_id": subnet_id,
                "ip_address": ip,
            }
            if mac is not None:
                entry["mac_address"] = mac
            body["ip_addresses"] = [entry]
        if port is not None:
            body["ports"] = [{"id": str(uuid.uuid4()), "number": port, "protocol": "Tcp"}]
        if service_name is not None:
            # 'Custom' is accepted by the CreateHostRequest deserializer; the
            # server normalizes unknown definitions, so never assert on it.
            body["services"] = [
                {
                    "id": str(uuid.uuid4()),
                    "service_definition": "Custom",
                    "name": service_name,
                }
            ]
        host = await self.data("POST", "/api/v1/hosts", json=body)
        self.created_host_ids.append(host["id"])
        return host

    async def delete_host(self, host_id: str) -> None:
        # 404 is fine: consolidation retires records, and tests may have
        # already cleaned up after themselves.
        await self.http.delete(f"/api/v1/hosts/{host_id}")


@pytest.fixture()
async def raw(settings: dict[str, str], live: None) -> AsyncIterator[RawScanopy]:
    async with httpx.AsyncClient(
        base_url=settings["base_url"],
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Accept": "application/json",
        },
        timeout=30.0,
    ) as http:
        helper = RawScanopy(http, settings["network_id"] or None)
        if helper.network_id is None:
            networks = await helper.data(
                "GET", "/api/v1/networks", params={"limit": 100, "offset": 0}
            )
            assert networks, "the test instance has no networks"
            helper.network_id = networks[0]["id"]
        try:
            yield helper
        finally:
            for host_id in helper.created_host_ids:
                await helper.delete_host(host_id)


# --------------------------------------------------------------------- helpers


def unique_name(suffix: str) -> str:
    return f"{TEST_PREFIX}-{suffix}-{uuid.uuid4().hex[:8]}"


def unique_ip() -> str:
    return f"10.99.{random.randint(1, 254)}.{random.randint(1, 254)}"
