"""Version compatibility guard (§5.4) — a hard gate, not a warning.

Scanopy is pre-1.0 and its own API docs state that breaking changes may land
in any release without an api_version bump (~30 releases in seven months).
Arborist therefore refuses to start against a server version outside the
range this build was verified against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import VersionCompatError

# Verified live against 0.17.3 (2026-07-06); 0.17.2 confirmed API-identical via
# the checked-in OpenAPI spec and docs. 0.18+ is unknown territory until re-verified.
MIN_SUPPORTED: tuple[int, int, int] = (0, 17, 2)
MAX_EXCLUSIVE: tuple[int, int, int] = (0, 18, 0)

SUPPORTED_API_VERSION = 1

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class CompatResult:
    server_version: str
    api_version: int | None
    ok: bool
    reason: str


def parse_version(version: str) -> tuple[int, int, int]:
    m = _SEMVER.match(version.strip())
    if not m:
        raise VersionCompatError(
            f"Could not parse Scanopy server_version {version!r}; refusing to guess."
        )
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def check_compat(server_version: str, api_version: int | None) -> CompatResult:
    """Check a live server's version against the supported range.

    Returns a result rather than raising so the caller can decide between
    hard-fail (default) and the explicit, loudly-logged override.
    """
    try:
        parsed = parse_version(server_version)
    except VersionCompatError as exc:
        return CompatResult(server_version, api_version, False, str(exc))

    if api_version is not None and api_version != SUPPORTED_API_VERSION:
        return CompatResult(
            server_version,
            api_version,
            False,
            f"Server reports api_version {api_version}; this Arborist build supports "
            f"api_version {SUPPORTED_API_VERSION}.",
        )
    if parsed < MIN_SUPPORTED:
        return CompatResult(
            server_version,
            api_version,
            False,
            f"Scanopy {server_version} is older than the oldest verified version "
            f"{_fmt(MIN_SUPPORTED)}.",
        )
    if parsed >= MAX_EXCLUSIVE:
        return CompatResult(
            server_version,
            api_version,
            False,
            f"Scanopy {server_version} is newer than the newest verified release line "
            f"(<{_fmt(MAX_EXCLUSIVE)}). Scanopy documents that breaking API changes may land "
            "in any pre-1.0 release, so Arborist refuses to run until this version is "
            "verified. Update Arborist, or set ARBORIST_ALLOW_UNTESTED_VERSION=true to "
            "proceed at your own risk.",
        )
    return CompatResult(server_version, api_version, True, "supported")


def _fmt(v: tuple[int, int, int]) -> str:
    return ".".join(str(p) for p in v)


def supported_range() -> str:
    return f">={_fmt(MIN_SUPPORTED)},<{_fmt(MAX_EXCLUSIVE)}"
