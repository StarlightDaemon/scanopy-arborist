# Changelog

## v0.1.0 — 2026-07-06 (first release)

First release of Arborist, an MCP server for [Scanopy](https://scanopy.net)
(verified against Scanopy 0.17.3; supported range `>=0.17.2,<0.18.0`).

### Core

- MCP tool surface in three tiers: 14 read-only tools (default profile), 11
  curated-write tools (`ARBORIST_PROFILE=readwrite` — host name/description/
  hidden, tags, bindings), and host consolidation behind its own opt-in flag
  (`ARBORIST_ENABLE_CONSOLIDATION`). Write tools never touch scanner-discovered
  data: host updates are read-modify-write, echo discovered fields verbatim,
  and never send child-sync arrays.
- Dual transport from one tool registry: stdio (default) and Streamable HTTP.
- Startup version-compat guard: refuses to run against an unverified Scanopy
  version (Scanopy documents pre-1.0 breaking changes in any release);
  `ARBORIST_ALLOW_UNTESTED_VERSION=true` is the explicit, logged override.
- HTTP hardening: non-loopback binds refused without a declared TLS posture
  (`ARBORIST_TLS_POSTURE`), DNS-rebinding host allowlist
  (`ARBORIST_ALLOWED_HOSTS`), constant-time bearer gate (`ARBORIST_AUTH_TOKEN`,
  distinct from the Scanopy API key by design).
- Outbound client hardening: TLS verification on by default with custom-CA
  support, `Retry-After`/`X-RateLimit-Remaining` handling, no unbounded
  pagination, retired-host-ID re-resolution by name/IP/MAC, actionable
  401/402/403 messages, content-type guard against Scanopy's SPA fallback.
- Credential-shaped fields redacted from every tool result.
- Two-phase bulk operations: bulk host updates, consolidation, and deletions
  return a diff/plan first and apply only when re-called with `confirm=true`.

### Fixed during pre-release review (same-session adversarial review + punch list)

- **Sentinel mismatch**: rename-only / hidden-only host updates crashed before
  any bytes were sent (module-local `_UNSET` object leaked into the payload).
- **Network-scope confinement**: `SCANOPY_NETWORK_ID` is now enforced on every
  write tool — including consolidation, tag assignment, and binding
  update/delete — not just host metadata updates. UUID lookups are not
  network-filtered server-side, so the client-side check is the enforcement.
- MAC matching requires a MAC-shaped selector; empty selectors are rejected.
- Full pagination in scans (no silent 2,000-record truncation; loud failure at
  a 50,000-record ceiling), and `list_hosts` search scans all pages.
- Explicit loopback DNS-rebinding allowlist covering non-standard loopback
  binds (e.g. `127.0.0.2`).
- Binding tools include the `network_id` Scanopy 0.17.3 requires.
- `Retry-After: 0` honored literally.
- `serverInfo.version` reports Arborist's version instead of the MCP SDK's.

### Distribution

- Docker: multi-stage uv Dockerfile (non-root runtime) + compose file.
- Podman: Quadlet unit (`deploy/podman/arborist.container`), verified rootful
  and rootless on a real Fedora CoreOS VM.
- Proxmox LXC: community-scripts-style `ct`/`install` pair, install path
  verified on a real Debian 13 VM (systemd unit lifecycle incl. reboot
  persistence); PVE-host flow pending ProxmoxVED submission.

### Known limitations

- No SVG topology export (Scanopy renders SVG client-side; Mermaid export is
  the machine-readable path). No Groups tools (no Groups REST resource in
  Scanopy 0.17.x; tags are the grouping mechanism).
- Install is from the git URL, not PyPI, for this release.
