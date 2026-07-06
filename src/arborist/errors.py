"""Error types and the Scanopy-status-to-actionable-message mapping."""

from __future__ import annotations

from typing import Any


class ArboristError(Exception):
    """Base class for all Arborist errors."""


class ConfigError(ArboristError):
    """Invalid or missing configuration; message lists every problem found."""


class VersionCompatError(ArboristError):
    """The target Scanopy server version is outside the tested range."""


class TransportSecurityError(ArboristError):
    """HTTP transport configuration violates the hardening rules (§5.5)."""


class ScanopyApiError(ArboristError):
    """An error response from the Scanopy API, with actionable guidance attached.

    Scanopy's envelope is ``{"success": false, "error": "...", "code"?: "...",
    "params"?: {...}}``. ``code``/``params`` are present on newer structured
    errors (e.g. ``entity_access_denied``).
    """

    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.code = code
        self.params = params or {}
        super().__init__(self.actionable())

    def actionable(self) -> str:
        """Map raw status codes to guidance the operator can act on."""
        base = f"Scanopy API error {self.status}: {self.message}"
        if self.code:
            base += f" (code: {self.code})"
        hint = _HINTS.get(self.status)
        if hint:
            return f"{base}\n{hint}"
        return base


_HINTS: dict[int, str] = {
    401: (
        "Check that SCANOPY_API_KEY is a user API key (starts with 'scp_u_'), is enabled and "
        "not expired, and that API access is enabled for your organization. Keys are managed in "
        "Scanopy under Platform > API Keys."
    ),
    402: (
        "Your Scanopy organization's plan does not include API access. Self-hosted Community "
        "Edition includes it; cloud Free/Starter plans do not."
    ),
    403: (
        "The API key lacks permission for this operation. Check the key's permission level "
        "(reads need Viewer, most writes need Member, tag creation needs Admin) and its network "
        "scoping — note that a key created with an empty network_ids list has access to NO "
        "networks, not all of them."
    ),
    404: (
        "The resource was not found. If this was a host ID that worked before, the record may "
        "have been retired by a consolidation (merged into another host); re-resolve it by "
        "name, IP, or MAC address."
    ),
    409: (
        "The request conflicts with existing state; Scanopy's message above describes the "
        "conflict. Common cases: duplicate tag name, binding type conflicts on the same "
        "IP/port, or deleting a host that has a daemon attached."
    ),
    429: (
        "Scanopy's rate limit was hit repeatedly (300 requests/minute, burst 150) and retries "
        "were exhausted. Wait a moment and try again, or batch fewer operations."
    ),
}


class HostNotFoundError(ScanopyApiError):
    """A host lookup failed even after re-resolution was attempted (§5.6).

    ``candidates`` carries near-miss hosts (matched loosely by name) so the
    caller can present alternatives instead of a dead-end 404.
    """

    def __init__(
        self,
        selector: str,
        *,
        attempted: list[str],
        candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.selector = selector
        self.candidates = candidates or []
        msg = (
            f"No host matched '{selector}' (tried: {', '.join(attempted)}). "
            "If this was a host ID from an earlier listing, the record may have been retired "
            "by consolidation — identify the host by name, IP, or MAC instead."
        )
        if self.candidates:
            names = ", ".join(
                f"{c.get('name')} ({c.get('id')})" for c in self.candidates[:5]
            )
            msg += f" Similarly named hosts: {names}"
        super(ScanopyApiError, self).__init__(msg)
        self.status = 404
        self.message = msg
        self.code = "host_not_found"
        self.params = {}
