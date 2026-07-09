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
  Proxmox LXC (`deploy/`), all still keyed on an `OWNER` placeholder pending
  publish.
- Confirmed: test suite and `.github/` CI workflow are in place; `.venv`,
  `.pytest_cache`, `.ruff_cache` present from local dev.
- Confirmed: RAIDEN Instance installed 2026-07-08. Repo now
  has a GitHub remote (`StarlightDaemon/scanopy-arborist`, public) as of this
  install — see `RAIDEN-ops/logs/DISTRIBUTION_LOG.md` and `Raiden-ops:LOOP-0021`.

## Constraints

- Confirmed: not yet published — `OWNER` is still a literal placeholder in
  `pyproject.toml`, the deploy configs, and docs. From-source install only
  until RELEASE.md's tag-cut sequence runs against the new remote.
- Confirmed: verified live only against Scanopy 0.17.3 (`>=0.17.2,<0.18.0`);
  Arborist refuses to start outside that range by design.

## Provenance

- RAIDEN Instance installed 2026-07-08, following the scan and
  install recorded under `Raiden-ops:LOOP-0021`.
- State captured from README.md, CHANGELOG.md, and docs/ at install time —
  not migrated from a prior ledger (this is the project's first RAIDEN state
  record).
