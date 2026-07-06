"""`arborist` CLI entrypoint.

Startup order is deliberate: parse config, then run the version-compat guard
(§5.4) against the target Scanopy, and only then bring up a transport. An
unrecognized server version is a refusal, not a warning.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import anyio

from . import __version__
from .client import ScanopyClient
from .compat import supported_range
from .config import Config
from .errors import ArboristError, ConfigError, TransportSecurityError, VersionCompatError
from .server import build_mcp, run_http

logger = logging.getLogger("arborist")

EXIT_CONFIG = 2
EXIT_VERSION = 3
EXIT_TRANSPORT = 4
EXIT_UNREACHABLE = 5


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    env = os.environ
    parser = argparse.ArgumentParser(
        prog="arborist",
        description="Arborist — MCP server for Scanopy (read your network from chat; "
        "curate names/tags/visibility without touching discovered data).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=env.get("ARBORIST_TRANSPORT", "stdio"),
        help="stdio (default; for local MCP clients) or http (Streamable HTTP).",
    )
    parser.add_argument(
        "--host",
        default=env.get("ARBORIST_BIND_HOST", "127.0.0.1"),
        help="HTTP bind host (default 127.0.0.1; non-loopback requires a declared "
        "ARBORIST_TLS_POSTURE).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(env.get("ARBORIST_BIND_PORT", "60074")),
        help="HTTP bind port (default 60074).",
    )
    parser.add_argument("--version", action="version", version=f"arborist {__version__}")
    return parser.parse_args(argv)


async def _version_guard(cfg: Config) -> None:
    """Run the §5.4 gate with a short-lived client (the serving transport owns
    its own client on its own event loop)."""
    guard_client = ScanopyClient(cfg)
    try:
        result = await guard_client.startup_guard()
    finally:
        await guard_client.aclose()
    if result.ok:
        logger.info(
            "connected to Scanopy %s (api_version %s) — within supported range %s",
            result.server_version, result.api_version, supported_range(),
        )
    else:
        logger.warning(
            "UNSUPPORTED Scanopy version %s — proceeding only because "
            "ARBORIST_ALLOW_UNTESTED_VERSION=true. Reason: %s",
            result.server_version, result.reason,
        )


def main(argv: list[str] | None = None) -> int:
    # stdout belongs to the stdio transport; all logging goes to stderr.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv)

    try:
        cfg = Config.from_env(os.environ)
    except ConfigError as exc:
        print(f"arborist: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    # Fail fast on transport misconfiguration, before touching the network.
    if args.transport == "http":
        try:
            cfg.validate_http_transport(args.host, args.port)
        except TransportSecurityError as exc:
            print(f"arborist: {exc}", file=sys.stderr)
            return EXIT_TRANSPORT

    try:
        anyio.run(_version_guard, cfg)
    except VersionCompatError as exc:
        print(
            f"arborist: refusing to start: {exc}\n"
            f"This build supports Scanopy {supported_range()}.",
            file=sys.stderr,
        )
        return EXIT_VERSION
    except ArboristError as exc:
        print(f"arborist: cannot reach Scanopy: {exc}", file=sys.stderr)
        return EXIT_UNREACHABLE
    except Exception as exc:  # connection refused, DNS, TLS handshake...
        print(
            f"arborist: cannot reach Scanopy at {cfg.base_url}: {exc}\n"
            "Check SCANOPY_BASE_URL and TLS settings (SCANOPY_TLS_VERIFY / "
            "SCANOPY_TLS_CA_PATH).",
            file=sys.stderr,
        )
        return EXIT_UNREACHABLE

    client = ScanopyClient(cfg)
    mcp = build_mcp(cfg, client, bind_host=args.host, bind_port=args.port)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        run_http(mcp, cfg, args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
