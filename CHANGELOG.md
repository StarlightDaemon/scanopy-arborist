# Changelog

## Unreleased

### Changed (scope-confinement audit, 2026-07-07)

- **`delete_tag` now always refuses under `SCANOPY_NETWORK_ID`.** The previous
  fail-closed design checked every entity the API key can see — but Scanopy
  0.17.3 also accepts tags on user API keys, which are *unreadable* under
  API-key auth (verified live: 403 "User context required" on
  `/api/v1/auth/keys` while tag assignment to the same key succeeds). No scan
  can prove an org-wide deletion stays inside a network scope, so scoped
  sessions refuse outright; delete tags from an unscoped Arborist (two-phase
  confirm unchanged) or the Scanopy UI. See `docs/scope-confinement-audit.md`.
- **`update_tag` fails closed on out-of-scope *visible* use.** Renaming/restyling
  a tag changes the label carried by every entity referencing it, so a scoped
  session now scans visible usage and refuses if any use is outside (or not
  attributable to) the configured network. **Known incomplete (F5 /
  Stop Condition 11):** a tag whose only use is on a `UserApiKey` — which an
  API key cannot read back — still passes this guard. The fix is more
  restrictive than the prior release (which had no `update_tag` scope check at
  all) but the residual is handed to a maintainer for a design decision; see
  `docs/scope-confinement-audit.md` §F5.
- **`tag_usage` rebuilt from an empirical probe** of all Scanopy resource
  types: scans all nine enumerable taggable types (was five — Daemon,
  DaemonApiKey, Discovery, Credential were missing) with list-shaped network
  attribution; org-scoped records with no network attribution classify as
  out-of-scope (fail closed). A live canary test re-derives the taggable set
  from the server and fails loudly if a Scanopy upgrade changes it.
- `update_host_metadata` applies the network-scope check before its no-op
  short-circuit (an out-of-scope host selected by UUID could previously have
  its metadata echoed back by a no-op update).
- Tag tool docstrings no longer claim deletion "removes the tag from every
  entity": deletion soft-closes the tag row (label destroyed org-wide);
  entity associations are left dangling (verified live).

### Fixed (second review pass)

- **Tag-object scope confinement (fail-closed).** `delete_tag` now enumerates
  every entity carrying the tag and refuses when `SCANOPY_NETWORK_ID` is set and
  any of them fall outside the configured network (deleting a tag strips it
  org-wide). `create_tag`/`update_tag` don't touch entity associations and
  proceed. Documented as the general policy for any org-scoped-but-not-network-
  scoped resource.
- `set_host_tags([])` now genuinely clears (Scanopy's assign endpoint no-ops on
  an empty list, so tags are removed individually) instead of silently
  reporting success while leaving tags in place.
- Non-JSON `text/plain` 4xx bodies from Scanopy (serde/path-param errors) are
  surfaced verbatim instead of the misleading "endpoint most likely does not
  exist" version-incompatibility hint (which is now reserved for actual
  `text/html` SPA fallbacks).
- `bulk_update_hosts` coerces `hidden` to a real boolean once, so the plan and
  apply phases can never disagree (`bool("false")` used to plan the opposite of
  what apply sent); un-coercible values become a clean per-row error.
- `update_host_metadata` rejects passing both `description` and
  `clear_description`, and short-circuits a no-op update instead of issuing a
  PUT that would move `updated_at`.
- Binding tools reject a `port_id` supplied with `binding_type="IPAddress"`
  instead of silently dropping it.
- `bulk_update_hosts` plan phase excludes out-of-scope hosts entirely (they
  become error rows) rather than echoing their name/description.

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
