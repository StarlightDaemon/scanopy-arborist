"""Configuration (§5.7) and transport-security validation (§5.5).

Two deliberately distinct env prefixes:
  SCANOPY_*  — the target Scanopy instance Arborist talks to
  ARBORIST_* — Arborist's own behavior
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

from .errors import ConfigError, TransportSecurityError


class Profile(str, Enum):
    READONLY = "readonly"
    READWRITE = "readwrite"


class TlsPosture(str, Enum):
    """Declared TLS posture for the HTTP transport (§5.5).

    loopback            — default; Arborist refuses to bind non-loopback.
    terminated-upstream — plain HTTP allowed on non-loopback binds because the
                          operator declares TLS/isolation is handled outside
                          (reverse proxy, container network, tunnel).
    direct              — Arborist serves TLS itself (cert/key required).
    """

    LOOPBACK = "loopback"
    TERMINATED_UPSTREAM = "terminated-upstream"
    DIRECT = "direct"


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _parse_bool(name: str, raw: str, errors: list[str]) -> bool:
    val = raw.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    errors.append(f"{name}={raw!r} is not a boolean (use true/false).")
    return False


def is_loopback_host(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Config:
    # SCANOPY_* — outbound connection to the Scanopy instance
    base_url: str
    api_key: str
    network_id: str | None
    tls_verify: bool
    tls_ca_path: str | None

    # ARBORIST_* — our own behavior
    profile: Profile
    enable_consolidation: bool
    auth_token: str | None
    allowed_hosts: list[str] = field(default_factory=list)
    tls_posture: TlsPosture = TlsPosture.LOOPBACK
    tls_cert_path: str | None = None
    tls_key_path: str | None = None
    allow_untested_version: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Config":
        errors: list[str] = []

        base_url = env.get("SCANOPY_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            errors.append("SCANOPY_BASE_URL is required (e.g. http://scanopy.lan:60072).")
        elif not base_url.startswith(("http://", "https://")):
            errors.append("SCANOPY_BASE_URL must start with http:// or https://.")

        api_key = env.get("SCANOPY_API_KEY", "").strip()
        if not api_key:
            errors.append(
                "SCANOPY_API_KEY is required (a Scanopy user API key, created under "
                "Platform > API Keys; starts with 'scp_u_')."
            )

        network_id = env.get("SCANOPY_NETWORK_ID", "").strip() or None

        tls_verify = True
        if "SCANOPY_TLS_VERIFY" in env:
            tls_verify = _parse_bool("SCANOPY_TLS_VERIFY", env["SCANOPY_TLS_VERIFY"], errors)

        tls_ca_path = env.get("SCANOPY_TLS_CA_PATH", "").strip() or None
        if tls_ca_path and not Path(tls_ca_path).is_file():
            errors.append(f"SCANOPY_TLS_CA_PATH points to a missing file: {tls_ca_path}")
        if tls_ca_path and not tls_verify:
            errors.append(
                "SCANOPY_TLS_CA_PATH is set but SCANOPY_TLS_VERIFY=false; pick one "
                "(a custom CA implies verification)."
            )

        profile_raw = env.get("ARBORIST_PROFILE", Profile.READONLY.value).strip().lower()
        try:
            profile = Profile(profile_raw)
        except ValueError:
            errors.append(
                f"ARBORIST_PROFILE={profile_raw!r} is invalid (use 'readonly' or 'readwrite')."
            )
            profile = Profile.READONLY

        enable_consolidation = False
        if "ARBORIST_ENABLE_CONSOLIDATION" in env:
            enable_consolidation = _parse_bool(
                "ARBORIST_ENABLE_CONSOLIDATION", env["ARBORIST_ENABLE_CONSOLIDATION"], errors
            )
        if enable_consolidation and profile is Profile.READONLY:
            errors.append(
                "ARBORIST_ENABLE_CONSOLIDATION=true requires ARBORIST_PROFILE=readwrite "
                "(consolidation is a write operation)."
            )

        auth_token = env.get("ARBORIST_AUTH_TOKEN", "").strip() or None
        allowed_hosts = [
            h.strip()
            for h in env.get("ARBORIST_ALLOWED_HOSTS", "").split(",")
            if h.strip()
        ]

        posture_raw = env.get("ARBORIST_TLS_POSTURE", TlsPosture.LOOPBACK.value).strip().lower()
        try:
            tls_posture = TlsPosture(posture_raw)
        except ValueError:
            errors.append(
                f"ARBORIST_TLS_POSTURE={posture_raw!r} is invalid "
                "(use 'loopback', 'terminated-upstream', or 'direct')."
            )
            tls_posture = TlsPosture.LOOPBACK

        tls_cert_path = env.get("ARBORIST_TLS_CERT_PATH", "").strip() or None
        tls_key_path = env.get("ARBORIST_TLS_KEY_PATH", "").strip() or None
        for label, p in (("ARBORIST_TLS_CERT_PATH", tls_cert_path), ("ARBORIST_TLS_KEY_PATH", tls_key_path)):
            if p and not Path(p).is_file():
                errors.append(f"{label} points to a missing file: {p}")

        allow_untested_version = False
        if "ARBORIST_ALLOW_UNTESTED_VERSION" in env:
            allow_untested_version = _parse_bool(
                "ARBORIST_ALLOW_UNTESTED_VERSION", env["ARBORIST_ALLOW_UNTESTED_VERSION"], errors
            )

        if errors:
            raise ConfigError("Configuration problems:\n- " + "\n- ".join(errors))

        return cls(
            base_url=base_url,
            api_key=api_key,
            network_id=network_id,
            tls_verify=tls_verify,
            tls_ca_path=tls_ca_path,
            profile=profile,
            enable_consolidation=enable_consolidation,
            auth_token=auth_token,
            allowed_hosts=allowed_hosts,
            tls_posture=tls_posture,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
            allow_untested_version=allow_untested_version,
        )

    def validate_http_transport(self, bind_host: str, bind_port: int) -> None:
        """Enforce §5.5 before the HTTP transport is allowed to start.

        Raises TransportSecurityError with every violation listed.
        """
        problems: list[str] = []
        loopback = is_loopback_host(bind_host)

        if not self.auth_token:
            problems.append(
                "ARBORIST_AUTH_TOKEN is required for the HTTP transport. It is Arborist's own "
                "gate secret, deliberately separate from the Scanopy API key."
            )
        elif len(self.auth_token) < 16:
            problems.append("ARBORIST_AUTH_TOKEN must be at least 16 characters.")

        if not loopback:
            if self.tls_posture is TlsPosture.LOOPBACK:
                problems.append(
                    f"Refusing to bind {bind_host}:{bind_port}: non-loopback binds require a "
                    "declared TLS posture. Set ARBORIST_TLS_POSTURE=terminated-upstream (TLS/"
                    "isolation handled by a reverse proxy or container network) or =direct "
                    "(Arborist serves TLS itself via ARBORIST_TLS_CERT_PATH/ARBORIST_TLS_KEY_PATH)."
                )
            if not self.allowed_hosts:
                problems.append(
                    "Non-loopback binds require ARBORIST_ALLOWED_HOSTS (comma-separated Host "
                    "header values, e.g. 'arborist.lan:60074') as DNS-rebinding protection."
                )

        if self.tls_posture is TlsPosture.DIRECT and not (self.tls_cert_path and self.tls_key_path):
            problems.append(
                "ARBORIST_TLS_POSTURE=direct requires both ARBORIST_TLS_CERT_PATH and "
                "ARBORIST_TLS_KEY_PATH."
            )

        if problems:
            raise TransportSecurityError(
                "HTTP transport refused (§5.5 hardening):\n- " + "\n- ".join(problems)
            )
