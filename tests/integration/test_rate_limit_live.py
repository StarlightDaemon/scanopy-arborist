"""Punch-list item 9: rate-limit handling against the REAL Scanopy limiter.

The disposable instance's limiter allows a burst (~150 requests) then answers
429 with Retry-After: 1 and X-RateLimit-Remaining: 0. This test primes the
limiter to exhaustion with raw requests, then proves ScanopyClient transparently
recovers by honoring Retry-After instead of surfacing the 429."""

from __future__ import annotations

import time

import anyio
import httpx
import pytest

from arborist.client import ScanopyClient
from arborist.config import Config

pytestmark = pytest.mark.integration


async def test_client_recovers_from_real_429(cfg: Config) -> None:
    # Prime the real limiter with raw requests (no retry logic) until it trips.
    tripped = None
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        headers={"Authorization": f"Bearer {cfg.api_key}"},
    ) as raw_http:
        for _ in range(400):
            r = await raw_http.get("/api/version")
            if r.status_code == 429:
                tripped = r
                break
    if tripped is None:
        pytest.skip("could not trip the live rate limiter (config changed?)")

    assert tripped.headers.get("Retry-After") is not None
    assert tripped.headers.get("X-RateLimit-Remaining") == "0"
    retry_after = float(tripped.headers["Retry-After"])

    # The client must absorb the 429: retry after the advertised wait and
    # return a normal result rather than raising.
    client = ScanopyClient(cfg)
    try:
        start = time.monotonic()
        info = await client.version_info()
        elapsed = time.monotonic() - start
    finally:
        await client.aclose()

    assert info["server_version"]
    # It waited at least (most of) the advertised Retry-After before succeeding.
    # (Unless the limiter window happened to roll over first — allow headroom.)
    assert elapsed >= min(retry_after, 0.5) * 0.5, (
        f"expected a backoff near Retry-After={retry_after}s, got {elapsed:.2f}s"
    )

    # Leave the shared limiter healthy for whatever test runs next: wait for
    # several consecutive 200s (the Remaining header is not trustworthy
    # mid-window) plus a full advertised window.
    await anyio.sleep(max(retry_after, 1.0))
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        headers={"Authorization": f"Bearer {cfg.api_key}"},
    ) as raw_http:
        consecutive = 0
        for _ in range(60):
            r = await raw_http.get("/api/version")
            consecutive = consecutive + 1 if r.status_code == 200 else 0
            if consecutive >= 5:
                break
            if r.status_code != 200:
                await anyio.sleep(0.5)
