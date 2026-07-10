# Current State

## Summary

- Confirmed: Arborist is a Python MCP server for Scanopy (self-hosted network
  topology tool), implemented at `src/`. Client, version guard, tool profiles
  (`readonly`/`readwrite`), and dual transport (stdio/http) are in place.
- Confirmed: hard scope-confinement boundary enforced — Arborist can read
  everything Scanopy discovers but can only write the curated overlay
  (name/description/hidden/tags/bindings), never the discovered layer.
- Confirmed: 2026-07-07 scope-confinement audit (finding F5) closed —
  `update_tag` and `delete_tag` now refuse unconditionally under
  `SCANOPY_NETWORK_ID` rather than trusting a tag-usage enumeration that has a
  structural blind spot (tags on user API keys are unreadable under API-key
  auth). See `docs/scope-confinement-audit.md`.
- Confirmed: deployment assets exist for Docker Compose, Podman Quadlet, and
  Proxmox LXC (`deploy/`), now keyed on the real owner (`StarlightDaemon` /
  `starlightdaemon` for lowercase image refs) as of the `v0.1.0` publish
  (LOOP-001, 2026-07-09). No container image has been pushed to GHCR yet;
  from-source and from-git-tag installs are the supported paths for this
  release.
- Confirmed: test suite and `.github/` CI workflow are in place; `.venv`,
  `.pytest_cache`, `.ruff_cache` present from local dev.
- Confirmed: RAIDEN Instance installed 2026-07-08. Repo now
  has a GitHub remote (`StarlightDaemon/scanopy-arborist`, public) as of this
  install — see `RAIDEN-ops/logs/DISTRIBUTION_LOG.md` and `Raiden-ops:LOOP-0021`.

## Constraints

- Confirmed: published — `v0.1.0` tagged and released on
  `github.com/StarlightDaemon/scanopy-arborist` (LOOP-001, 2026-07-09), per
  RELEASE.md's tag-cut sequence. `pyproject.toml` version and
  `arborist --version` both read `0.1.0` (the prior `0.1.0b1` beta suffix is
  gone).
- Confirmed: verified live only against Scanopy 0.17.3 (`>=0.17.2,<0.18.0`);
  Arborist refuses to start outside that range by design.

## Provenance

- RAIDEN Instance installed 2026-07-08, following the scan and
  install recorded under `Raiden-ops:LOOP-0021`.
- State captured from README.md, CHANGELOG.md, and docs/ at install time —
  not migrated from a prior ledger (this is the project's first RAIDEN state
  record).
