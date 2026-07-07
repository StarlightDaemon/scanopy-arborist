"""Canary: re-derive Scanopy's tag reach empirically and fail LOUDLY on drift.

The two SC8 escapes both had the same anatomy: a hand-enumerated list of
taggable entity types that was narrower than what the server actually accepts.
This canary removes the hand from the loop:

1. The full entity_type enum is extracted from the server itself — an
   unknown-variant probe makes serde enumerate every accepted spelling in its
   error message.
2. Every variant is then probed against PUT /api/v1/tags/assign; the server
   answers "Entity type X does not support tagging" for non-taggable ones, so
   the taggable set is derived from live behavior, not from documentation,
   reviews, or source reading.
3. The derived set must equal ScanopyClient's hardcoded reach constants
   (_TAG_USAGE_SOURCES + TAG_USAGE_BLIND_TYPES) exactly.
4. The enumerability split is re-verified: every _TAG_USAGE_SOURCES path must
   list under API-key auth WITH the attribution field the client expects, and
   every blind type must still be unreadable. If Scanopy ever makes user API
   keys readable to API keys, this fails so delete_tag's unconditional scoped
   refusal can be revisited.

Runs against the pinned disposable instance (same rails as the whole
integration suite). If this canary fails after a Scanopy upgrade, update
_TAG_USAGE_SOURCES / TAG_USAGE_BLIND_TYPES from the probe output in the
failure message — never by hand-picking types.
"""

from __future__ import annotations

import re
import uuid

import pytest

from arborist.client import ScanopyClient
from arborist.tools.write import _TAGGABLE

from .conftest import RawScanopy

pytestmark = pytest.mark.integration

# The taggable set verified for the pinned Scanopy line (0.17.x), 2026-07-07.
EXPECTED_TAGGABLE = {
    "Host", "Service", "Subnet", "Network", "Dependency",
    "Daemon", "DaemonApiKey", "UserApiKey", "Credential", "Discovery",
}

_VARIANT = re.compile(r"`([A-Za-z0-9_]+)`")


async def _raw_status(raw: RawScanopy, method: str, path: str, **kw):
    # Retry 429s: the live limiter is shared with the rest of the suite, and
    # the enum probe alone issues ~25 requests back-to-back.
    import anyio

    for _ in range(8):
        resp = await raw.http.request(method, path, **kw)
        if resp.status_code != 429:
            return resp
        wait = resp.headers.get("Retry-After")
        await anyio.sleep(
            float(wait) if wait and wait.replace(".", "").isdigit() else 1.0
        )
    return resp


async def _derive_entity_enum(raw: RawScanopy) -> set[str]:
    """serde's unknown-variant error enumerates every accepted variant."""
    resp = await _raw_status(
        raw, "PUT", "/api/v1/tags/assign",
        json={"entity_type": "__arborist_canary__",
              "entity_id": str(uuid.uuid4()), "tag_ids": []},
    )
    text = resp.text
    assert "unknown variant" in text, (
        f"expected serde unknown-variant error, got HTTP {resp.status_code}: {text[:300]}"
    )
    variants = set(_VARIANT.findall(text.split("expected", 1)[-1]))
    assert variants, f"could not parse variants from: {text[:300]}"
    return variants


async def _derive_taggable(raw: RawScanopy, variants: set[str]) -> set[str]:
    """A variant is taggable iff the assign endpoint does not reject it with
    the runtime 'does not support tagging' branch. (Entity existence is not
    checked for an empty tag_ids list, so no fixtures are needed.)"""
    taggable = set()
    for v in sorted(variants):
        resp = await _raw_status(
            raw, "PUT", "/api/v1/tags/assign",
            json={"entity_type": v, "entity_id": str(uuid.uuid4()), "tag_ids": []},
        )
        if resp.status_code < 400:
            taggable.add(v)
            continue
        body = resp.text
        assert "does not support tagging" in body, (
            f"unexpected rejection probing entity_type={v}: "
            f"HTTP {resp.status_code} {body[:200]}"
        )
    return taggable


async def test_taggable_set_matches_client_constants(raw: RawScanopy) -> None:
    variants = await _derive_entity_enum(raw)
    taggable = await _derive_taggable(raw, variants)

    hardcoded = set(ScanopyClient._TAG_USAGE_SOURCES) | set(
        ScanopyClient.TAG_USAGE_BLIND_TYPES
    )
    assert taggable == hardcoded == EXPECTED_TAGGABLE, (
        "Scanopy's live taggable set drifted from Arborist's hardcoded reach.\n"
        f"  live probe:   {sorted(taggable)}\n"
        f"  client const: {sorted(hardcoded)}\n"
        f"  pinned:       {sorted(EXPECTED_TAGGABLE)}\n"
        "Update _TAG_USAGE_SOURCES/TAG_USAGE_BLIND_TYPES from the live probe "
        "(re-derive attribution per type), never by hand."
    )
    # Arborist's own tag tools must stay within the server's taggable set AND
    # within the enumerable (scope-checkable) subset.
    assert _TAGGABLE <= taggable
    assert _TAGGABLE <= set(ScanopyClient._TAG_USAGE_SOURCES)


async def test_enumerable_types_list_with_expected_attribution(
    raw: RawScanopy,
) -> None:
    """Every path tag_usage scans must (a) answer a JSON list under API-key
    auth and (b) expose the attribution field the client reads. Instances are
    created where the standard test instance may not have any."""
    org_id = (await raw.data("GET", "/api/v1/networks"))[0]["organization_id"]
    created: list[str] = []  # (path with id) to DELETE at teardown
    try:
        dep = await raw.data(
            "POST", "/api/v1/dependencies",
            json={"name": f"arborist-canary-dep-{uuid.uuid4().hex[:6]}",
                  "description": None, "network_id": raw.network_id,
                  "dependency_type": "RequestPath", "color": "Gray"},
        )
        created.append(f"/api/v1/dependencies/{dep['id']}")
        cred = await raw.data(
            "POST", "/api/v1/credentials",
            json={"name": f"arborist-canary-cred-{uuid.uuid4().hex[:6]}",
                  "organization_id": org_id, "assigned_network_ids": [],
                  "description": None,
                  "credential_type": {"type": "SnmpV2c",
                                      "community": {"mode": "Inline",
                                                    "value": "public"}}},
        )
        created.append(f"/api/v1/credentials/{cred['id']}")

        problems: list[str] = []
        for etype, (path, kind) in ScanopyClient._TAG_USAGE_SOURCES.items():
            resp = await _raw_status(raw, "GET", path, params={"limit": 200})
            ct = resp.headers.get("content-type", "")
            if resp.status_code != 200 or not ct.startswith("application/json"):
                problems.append(
                    f"{etype}: {path} not listable under API key "
                    f"(HTTP {resp.status_code}, {ct})"
                )
                continue
            items = resp.json().get("data") or []
            if not items:
                problems.append(
                    f"{etype}: no instance available on the test instance to "
                    f"verify attribution field — canary requires one"
                )
                continue
            field = "id" if kind == "self" else (
                "network_id" if kind == "network_id" else kind.split(":", 1)[1]
            )
            if field not in items[0]:
                problems.append(
                    f"{etype}: expected attribution field {field!r} missing from "
                    f"{path} records (saw {sorted(items[0].keys())})"
                )
            if "tags" not in items[0]:
                problems.append(
                    f"{etype}: records from {path} no longer expose 'tags' — "
                    f"tag_usage would silently miss this type"
                )
        assert not problems, "tag_usage sources drifted:\n  " + "\n  ".join(problems)
    finally:
        for path in created:
            await raw.data("DELETE", path)


async def test_blind_types_are_still_blind(raw: RawScanopy) -> None:
    """UserApiKey lists/GETs must still be unreadable under API-key auth. If
    this fails, Scanopy opened them up — a GOOD change: tag_usage can then
    enumerate them and delete_tag's unconditional scoped refusal should be
    revisited (see docs/scope-confinement-audit.md)."""
    assert set(ScanopyClient.TAG_USAGE_BLIND_TYPES) == {"UserApiKey"}
    resp = await _raw_status(raw, "GET", "/api/v1/auth/keys", params={"limit": 1})
    ok_json_list = (
        resp.status_code == 200
        and resp.headers.get("content-type", "").startswith("application/json")
        and isinstance(resp.json().get("data"), list)
    )
    assert not ok_json_list, (
        "/api/v1/auth/keys is now readable under API-key auth — the UserApiKey "
        "blind spot is gone. Add it to _TAG_USAGE_SOURCES (attribution: "
        "network_ids:network_ids) and reconsider delete_tag's unconditional "
        "scoped refusal."
    )
