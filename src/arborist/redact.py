"""Output hygiene (§5.8): redact credential-shaped fields from API payloads.

Every tool result passes through :func:`redact` before it reaches the model.
Redaction is by key name, recursively, and intentionally errs on the side of
masking too much (e.g. credential IDs) rather than too little.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# Key names whose values are credential-shaped. "key" alone is included on
# purpose: Scanopy uses bare "key" for API-key material (already server-masked,
# but we do not rely on that).
_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passphrase|secret|token|api[-_]?key|apikey|private[-_]?key"
    r"|credential|session|authorization|^key$)"
)


def is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY.search(key))


def redact(value: Any) -> Any:
    """Return a deep copy of ``value`` with credential-shaped fields masked.

    Scalar values under a sensitive key are replaced with ``[REDACTED]``;
    containers under a sensitive key are replaced wholesale (a list of
    credential assignments is as sensitive as a single one).
    """
    return _walk(value, parent_sensitive=False)


def _walk(value: Any, *, parent_sensitive: bool) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if is_sensitive_key(str(k)):
                out[k] = REDACTED
            else:
                out[k] = _walk(v, parent_sensitive=False)
        return out
    if isinstance(value, list):
        return [_walk(v, parent_sensitive=parent_sensitive) for v in value]
    if parent_sensitive and isinstance(value, (str, int, float)):
        return REDACTED
    return value
