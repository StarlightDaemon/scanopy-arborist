"""Thin Scanopy API client (§5.2) — every HTTP call Arborist makes lives here.

Hardening per §5.6:
- TLS verification on by default, custom CA supported.
- 429s retried honoring Retry-After; X-RateLimit-Remaining respected proactively.
- Pagination never uses limit=0 (Scanopy treats 0 as "no limit").
- 404 on a host ID triggers re-resolution by name/IP/MAC before failing.
- 401/403/402 mapped to actionable messages (see errors.py).
- Because Scanopy's SPA catch-all answers *unknown* /api paths with 200 text/html,
  every response is content-type-checked before parsing.

Write safety per §2: the only write paths are curated-overlay fields. Host
updates are read-modify-write: current discovered-layer values are echoed back
verbatim and child arrays (ip_addresses/ports/services/credential_assignments)
are always omitted, which Scanopy documents as "preserve existing".
"""

from __future__ import annotations

import re
import uuid as uuid_mod
from typing import Any, Sequence

import anyio
import httpx

from .compat import CompatResult, check_compat
from .config import Config
from .errors import (
    ArboristError,
    HostNotFoundError,
    ScanopyApiError,
    VersionCompatError,
)

_UNSET = object()

_MAX_RETRIES = 3
_MAX_RETRY_WAIT_S = 30.0
_PAGE_SIZE = 200
_SCAN_CEILING = 50_000


class AmbiguousSelectorError(ArboristError):
    """A host selector matched more than one host."""


def _is_uuid(value: str) -> bool:
    try:
        uuid_mod.UUID(value)
        return True
    except ValueError:
        return False


_MAC_SHAPE = re.compile(
    r"^[0-9A-Fa-f]{2}([:.\-]?[0-9A-Fa-f]{2}){5}$"
)


def _norm_mac(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _looks_like_mac(value: str) -> bool:
    """Only selectors shaped like a MAC participate in MAC matching — stripping
    arbitrary strings down to their hex residue produces false positives."""
    return bool(_MAC_SHAPE.match(value.strip()))


def clamp_limit(limit: int | None, default: int = 100) -> int:
    """Pagination guard: Scanopy's limit=0 means unbounded — never send it."""
    if limit is None:
        limit = default
    return max(1, min(int(limit), 1000))


class ScanopyClient:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._org_id: str | None = None
        verify: bool | str = cfg.tls_ca_path if cfg.tls_ca_path else cfg.tls_verify
        self._http = httpx.AsyncClient(
            base_url=cfg.base_url,
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Accept": "application/json",
            },
            verify=verify,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=60.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ core

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        raw_text: bool = False,
    ) -> Any:
        resp: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            resp = await self._http.request(method, path, params=params, json=json_body)
            if resp.status_code != 429 or attempt == _MAX_RETRIES:
                break
            wait = _retry_after_seconds(resp)
            if wait is None:
                wait = 2.0 * (attempt + 1)
            await anyio.sleep(min(wait, _MAX_RETRY_WAIT_S))
        assert resp is not None

        # Proactive backoff when the rate-limit budget is nearly spent.
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) <= 3:
            await anyio.sleep(0.5)

        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()

        if raw_text and resp.status_code < 400 and content_type != "text/html":
            return resp.text

        if content_type != "application/json":
            # Scanopy answers *unknown* /api paths with its SPA HTML shell (200
            # text/html) — that genuinely means "endpoint not on this version".
            # But real 4xx errors arrive as text/plain (axum path-param parse
            # failures -> 400, serde body rejections -> 422); surface those
            # verbatim instead of the misleading version-incompatibility hint.
            if content_type == "text/html":
                raise ScanopyApiError(
                    resp.status_code,
                    f"Non-JSON (text/html) response from {method} {path}. Scanopy's web UI "
                    "answers unknown API paths with its HTML shell, so this endpoint most "
                    "likely does not exist on the connected server version.",
                )
            body = resp.text.strip()
            raise ScanopyApiError(
                resp.status_code,
                body[:500]
                if body
                else f"Non-JSON ({content_type or 'no content-type'}) response "
                f"from {method} {path}.",
            )

        try:
            envelope = resp.json()
        except ValueError as exc:
            raise ScanopyApiError(
                resp.status_code, f"Unparseable JSON from {method} {path}: {exc}"
            ) from exc

        if isinstance(envelope, dict) and envelope.get("success") is True:
            return envelope.get("data")

        message = "unknown error"
        code = None
        params_out: dict[str, Any] | None = None
        if isinstance(envelope, dict):
            message = str(envelope.get("error", message))
            code = envelope.get("code")
            params_out = envelope.get("params")
        raise ScanopyApiError(resp.status_code, message, code=code, params=params_out)

    async def _get_page(
        self, path: str, *, params: dict[str, Any] | None = None, limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        q = dict(params or {})
        q["limit"] = clamp_limit(limit)
        q["offset"] = max(0, int(offset))
        data = await self._request("GET", path, params=q)
        return data if isinstance(data, list) else []

    async def _get_all(
        self, path: str, *, params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch every page. A silent cap here would make resolution and scans
        wrong on large instances, so instead of truncating we fail loudly at an
        absurd ceiling (misconfiguration / runaway pagination guard)."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self._get_page(path, params=params, limit=_PAGE_SIZE, offset=offset)
            items.extend(page)
            if len(page) < _PAGE_SIZE:
                return items
            if len(items) >= _SCAN_CEILING:
                raise ArboristError(
                    f"Scan of {path} exceeded {_SCAN_CEILING} records without finishing; "
                    "refusing to continue. Narrow the query (network_id, tag filters) "
                    "instead of scanning the whole instance."
                )
            offset += _PAGE_SIZE

    def _network_params(self, network_id: str | None = None) -> dict[str, Any]:
        nid = network_id or self._cfg.network_id
        return {"network_id": nid} if nid else {}

    # --------------------------------------------------------------- version

    async def version_info(self) -> dict[str, Any]:
        return await self._request("GET", "/api/version")

    async def startup_guard(self) -> CompatResult:
        """§5.4 hard gate. Raises VersionCompatError unless the override is set."""
        info = await self.version_info()
        result = check_compat(
            str(info.get("server_version", "")), info.get("api_version")
        )
        if not result.ok and not self._cfg.allow_untested_version:
            raise VersionCompatError(result.reason)
        return result

    # ----------------------------------------------------------------- reads

    async def list_networks(self) -> list[dict[str, Any]]:
        return await self._get_all("/api/v1/networks")

    async def list_hosts(
        self,
        *,
        network_id: str | None = None,
        tag_ids: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params = self._network_params(network_id)
        if tag_ids:
            params["tag_ids"] = ",".join(tag_ids)
        return await self._get_page("/api/v1/hosts", params=params, limit=limit, offset=offset)

    async def get_host(self, host_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/hosts/{host_id}")

    async def list_all_hosts(
        self, *, network_id: str | None = None, tag_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Every host (all pages) — for client-side filtering like substring search,
        which must never be applied to a single server-side page."""
        params = self._network_params(network_id)
        if tag_ids:
            params["tag_ids"] = ",".join(tag_ids)
        return await self._get_all("/api/v1/hosts", params=params)

    async def get_service(self, service_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/services/{service_id}")

    async def list_services(
        self, *, network_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self._get_page(
            "/api/v1/services", params=self._network_params(network_id), limit=limit,
            offset=offset,
        )

    async def list_subnets(self, *, network_id: str | None = None) -> list[dict[str, Any]]:
        return await self._get_all("/api/v1/subnets", params=self._network_params(network_id))

    async def list_ports(
        self, *, network_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self._get_page(
            "/api/v1/ports", params=self._network_params(network_id), limit=limit, offset=offset
        )

    async def list_ip_addresses(
        self, *, network_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self._get_page(
            "/api/v1/ip-addresses", params=self._network_params(network_id), limit=limit,
            offset=offset,
        )

    async def list_snmp_interfaces(
        self, *, network_id: str | None = None, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self._get_page(
            "/api/v1/if-entries", params=self._network_params(network_id), limit=limit,
            offset=offset,
        )

    async def list_dependencies(self, *, network_id: str | None = None) -> list[dict[str, Any]]:
        return await self._get_all(
            "/api/v1/dependencies", params=self._network_params(network_id)
        )

    async def list_tags(self) -> list[dict[str, Any]]:
        return await self._get_all("/api/v1/tags")

    async def list_bindings(self, *, network_id: str | None = None) -> list[dict[str, Any]]:
        return await self._get_all("/api/v1/bindings", params=self._network_params(network_id))

    async def list_topologies(self, *, network_id: str | None = None) -> list[dict[str, Any]]:
        return await self._get_all("/api/v1/topology", params=self._network_params(network_id))

    async def export_topology_mermaid(self, topology_id: str, *, view: str | None = None) -> str:
        params = {"view": view} if view else None
        return await self._request(
            "GET", f"/api/v1/topology/{topology_id}/export/mermaid", params=params,
            raw_text=True,
        )

    # ------------------------------------------------------- host resolution

    async def resolve_host(self, selector: str) -> dict[str, Any]:
        """Resolve a host by UUID, name, hostname, IP, or MAC (§5.6).

        A UUID that 404s falls back to a scan so a consolidation-retired ID
        still produces useful candidates instead of a bare 404.
        """
        s = selector.strip()
        if not s:
            raise ArboristError(
                "Host selector must not be empty; pass an id, name, hostname, IP, or MAC."
            )
        attempted: list[str] = []

        if _is_uuid(s):
            attempted.append("id")
            try:
                return await self.get_host(s)
            except ScanopyApiError as exc:
                if exc.status != 404:
                    raise
                # Retired ID (consolidation deletes merged records): fall through.

        hosts = await self._get_all("/api/v1/hosts", params=self._network_params())
        attempted.extend(["name", "hostname", "ip", "mac"])

        lowered = s.lower()
        mac = _norm_mac(s) if _looks_like_mac(s) else ""

        def matches(h: dict[str, Any]) -> bool:
            if str(h.get("name", "")).lower() == lowered:
                return True
            hostname = (h.get("hostname") or "").lower()
            if hostname and hostname == lowered:
                return True
            for ip in h.get("ip_addresses", []):
                if ip.get("ip_address") == s:
                    return True
                if mac and _norm_mac(ip.get("mac_address") or "") == mac:
                    return True
            return False

        found = [h for h in hosts if matches(h)]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            names = ", ".join(f"{h['name']} ({h['id']})" for h in found[:10])
            raise AmbiguousSelectorError(
                f"Selector '{selector}' matched {len(found)} hosts: {names}. "
                "Use the host id to disambiguate."
            )

        candidates = [h for h in hosts if lowered and lowered in str(h.get("name", "")).lower()]
        raise HostNotFoundError(
            selector,
            attempted=attempted,
            candidates=[{"id": h["id"], "name": h.get("name")} for h in candidates],
        )

    # ---------------------------------------------------------------- writes

    def assert_in_scope(self, record: dict[str, Any], *, kind: str = "Host") -> None:
        """SCANOPY_NETWORK_ID, when set, confines writes to that network.

        Every write tool must funnel through this for any record it resolved —
        UUID lookups are not network-filtered server-side, so this client-side
        check is the only scope enforcement that exists."""
        nid = self._cfg.network_id
        if nid and str(record.get("network_id")) != nid:
            raise ArboristError(
                f"{kind} '{record.get('name', record.get('id'))}' ({record.get('id')}) belongs "
                f"to network {record.get('network_id')}, but Arborist is scoped to network "
                f"{nid} (SCANOPY_NETWORK_ID). Refusing to modify it."
            )


    async def update_host_curated(
        self,
        host_id: str,
        *,
        name: str | None = None,
        description: Any = _UNSET,
        hidden: bool | None = None,
        tags: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Update only curated-overlay fields on a host (§2).

        Read-modify-write against the current record:
        - discovered/scalar fields (hostname, virtualization) echoed verbatim —
          Scanopy's PUT is full-replace for scalars, so omitting them would
          clear discovered data;
        - `tags` echoed unless explicitly replaced — Scanopy clears tags when
          the field is omitted;
        - child arrays always omitted, which Scanopy documents as "preserve";
        - expected_updated_at passed for optimistic locking, so a concurrent
          change (e.g. a scan) surfaces as a conflict instead of a lost update.
        """
        current = await self.get_host(host_id)
        self.assert_in_scope(current)

        payload: dict[str, Any] = {
            "id": current["id"],
            "name": name if name is not None else current["name"],
            "hostname": current.get("hostname"),
            "description": (
                current.get("description") if description is _UNSET else description
            ),
            "hidden": hidden if hidden is not None else current["hidden"],
            "tags": list(tags) if tags is not None else list(current.get("tags", [])),
            "virtualization": current.get("virtualization"),
            "expected_updated_at": current.get("updated_at"),
        }
        return await self._request(
            "PUT", f"/api/v1/hosts/{current['id']}", json_body=payload
        )

    # Tags ------------------------------------------------------------------

    async def organization_id(self) -> str:
        """The caller's organization id (needed by tag creation), fetched once."""
        if getattr(self, "_org_id", None) is None:
            self._org_id = await self._discover_organization_id()
        return self._org_id

    async def _discover_organization_id(self) -> str:
        # /api/v1/organizations requires a user session on 0.17.3 — under
        # API-key auth it answers 403 "User context required" — so fall back
        # to the organization id every network record carries.
        try:
            orgs = await self._get_all("/api/v1/organizations")
            if orgs:
                return str(orgs[0]["id"])
        except ScanopyApiError as exc:
            if exc.status not in (401, 402, 403):
                raise
        for net in await self.list_networks():
            if net.get("organization_id"):
                return str(net["organization_id"])
        raise ArboristError("Could not determine organization id from the API key.")

    async def create_tag(
        self,
        name: str,
        *,
        color: str = "Gray",
        description: str | None = None,
        is_application: bool = False,
    ) -> dict[str, Any]:
        # Scanopy's Tag deserializer requires every TagBase field to be present,
        # including a nullable description and the organization id.
        body: dict[str, Any] = {
            "name": name,
            "color": color,
            "description": description,
            "is_application": is_application,
            "organization_id": await self.organization_id(),
        }
        return await self._request("POST", "/api/v1/tags", json_body=body)

    async def update_tag(self, tag_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = await self._request("GET", f"/api/v1/tags/{tag_id}")
        merged = {**current, **patch, "id": tag_id}
        return await self._request("PUT", f"/api/v1/tags/{tag_id}", json_body=merged)

    async def delete_tag(self, tag_id: str) -> None:
        await self._request("DELETE", f"/api/v1/tags/{tag_id}")

    # Tag-reach ground truth for Scanopy 0.17.3, derived EMPIRICALLY by probing
    # PUT /api/v1/tags/assign with every resource type against a live instance
    # (2026-07-07), then cross-checked against EntityDiscriminants::is_taggable
    # in the Scanopy source. Ten types accept tag assignment:
    #
    #   enumerable under API-key auth (the nine below), plus
    #   UserApiKey — whose list/GET endpoints (/api/v1/auth/keys) answer
    #   403 "User context required" under API-key auth, so assignments to user
    #   API keys are INVISIBLE to Arborist. tag_usage() therefore can never be
    #   a complete census, which is why org-wide destructive tag operations
    #   fail closed under a network scope instead of trusting this scan.
    #
    # tests/integration/test_tag_scope_canary.py re-derives both sets against
    # the pinned Scanopy version and fails loudly if they drift from these
    # constants. Do NOT extend by hand — re-run the canary/probe instead.
    #
    # Attribution kinds:
    #   "network_id"  — record carries a scalar network_id
    #   "self"        — the record IS a network; its own id is the attribution
    #   "network_ids:<field>" — org-scoped record carrying a LIST of network
    #       ids under <field>; an empty list means the record is attributable
    #       to no network at all (treated as outside any scope — fail closed)
    _TAG_USAGE_SOURCES: dict[str, tuple[str, str]] = {
        "Host": ("/api/v1/hosts", "network_id"),
        "Service": ("/api/v1/services", "network_id"),
        "Subnet": ("/api/v1/subnets", "network_id"),
        "Network": ("/api/v1/networks", "self"),
        "Dependency": ("/api/v1/dependencies", "network_id"),
        "Daemon": ("/api/v1/daemons", "network_id"),
        "DaemonApiKey": ("/api/v1/auth/daemon", "network_id"),
        "Discovery": ("/api/v1/discovery", "network_id"),
        "Credential": ("/api/v1/credentials", "network_ids:assigned_network_ids"),
    }

    #: Taggable types whose assignments tag_usage() CANNOT see under API-key
    #: auth (verified live: 403 on list and GET). Their existence is the reason
    #: scoped tag deletion refuses outright rather than trusting the scan.
    TAG_USAGE_BLIND_TYPES: tuple[str, ...] = ("UserApiKey",)

    async def tag_usage(self, tag_id: str) -> list[dict[str, Any]]:
        """Every VISIBLE entity currently carrying ``tag_id``, across ALL
        networks the API key can see (no network filter), as
        ``{entity_type, id, name, network_ids, org_scoped}`` where
        ``network_ids`` is the record's full network attribution ([] when it
        has none).

        Deliberately does NOT apply SCANOPY_NETWORK_ID scoping — its purpose is
        to reveal out-of-scope uses so mutations can fail closed. NOT a
        complete census: types in TAG_USAGE_BLIND_TYPES are unreadable under
        API-key auth and never appear here.
        """
        usage: list[dict[str, Any]] = []
        for etype, (path, kind) in self._TAG_USAGE_SOURCES.items():
            for e in await self._get_all(path):
                if tag_id not in (e.get("tags") or []):
                    continue
                if kind == "self":
                    nets = [e["id"]]
                elif kind == "network_id":
                    nets = [e["network_id"]] if e.get("network_id") else []
                else:  # "network_ids:<field>"
                    nets = list(e.get(kind.split(":", 1)[1]) or [])
                usage.append(
                    {
                        "entity_type": etype,
                        "id": e["id"],
                        "name": e.get("name"),
                        "network_ids": [str(n) for n in nets],
                        "org_scoped": kind.startswith("network_ids:"),
                    }
                )
        return usage

    def usage_outside_scope(self, usage: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The subset of tag_usage() records not PROVABLY inside the configured
        network scope. A record counts as outside when any of its network ids
        differ from the scope, or when it has no network attribution at all
        (org-scoped records with an empty list — fail closed on the unknown).
        Returns [] when no scope is configured."""
        nid = self._cfg.network_id
        if not nid:
            return []
        outside: list[dict[str, Any]] = []
        for u in usage:
            nets = u.get("network_ids") or []
            if not nets or set(nets) != {nid}:
                outside.append(u)
        return outside

    async def set_entity_tags(
        self, entity_type: str, entity_id: str, tag_ids: Sequence[str]
    ) -> dict[str, Any] | None:
        return await self._request(
            "PUT",
            "/api/v1/tags/assign",
            json_body={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "tag_ids": list(tag_ids),
            },
        )

    async def bulk_tag(
        self, tag_id: str, entity_type: str, entity_ids: Sequence[str], *, remove: bool = False
    ) -> dict[str, Any] | None:
        op = "bulk-remove" if remove else "bulk-add"
        return await self._request(
            "POST",
            f"/api/v1/tags/assign/{op}",
            json_body={
                "entity_type": entity_type,
                "entity_ids": list(entity_ids),
                "tag_id": tag_id,
            },
        )

    async def resolve_tag(self, selector: str) -> dict[str, Any]:
        s = selector.strip()
        tags = await self.list_tags()
        if _is_uuid(s):
            for t in tags:
                if t["id"] == s:
                    return t
            raise ArboristError(f"No tag with id {s}.")
        matches = [t for t in tags if t["name"].lower() == s.lower()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            known = ", ".join(sorted(t["name"] for t in tags)) or "(none)"
            raise ArboristError(f"No tag named '{selector}'. Existing tags: {known}")
        raise AmbiguousSelectorError(f"Tag name '{selector}' matched {len(matches)} tags.")

    # Bindings ---------------------------------------------------------------

    async def get_binding(self, binding_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/bindings/{binding_id}")

    async def create_binding(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/bindings", json_body=body)

    async def update_binding(self, binding_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "PUT", f"/api/v1/bindings/{binding_id}", json_body={**body, "id": binding_id}
        )

    async def delete_binding(self, binding_id: str) -> None:
        await self._request("DELETE", f"/api/v1/bindings/{binding_id}")

    # Consolidation ----------------------------------------------------------

    async def consolidate_hosts(
        self, destination_id: str, other_id: str
    ) -> dict[str, Any]:
        """Merge other's interfaces/services/ports into destination; Scanopy
        deletes the source record. Validation (same-host, cross-network,
        daemon-attached source) is surfaced from the server's 400s."""
        return await self._request(
            "PUT", f"/api/v1/hosts/{destination_id}/consolidate/{other_id}"
        )


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
