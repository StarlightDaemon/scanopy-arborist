# Open Loops

Work must be executed one loop at a time.

## LOOP-001: publish the repo (fill in `OWNER`, cut v0.1.0)

- Status: open
- Scope: replace the `OWNER` placeholder across `pyproject.toml`,
  `deploy/docker/docker-compose.yml`, `deploy/podman/arborist.container`,
  `deploy/lxc/`, and the README/docs with `starlightdaemon` (now that the
  GitHub remote exists), then run the `RELEASE.md` sequence to cut `v0.1.0`.
- Readiness: ready — GitHub remote now exists
  (`StarlightDaemon/scanopy-arborist`), which was the blocking precondition.
- Closure condition: `OWNER` placeholder fully resolved, `v0.1.0` tagged and
  pushed, install instructions in README/docs/usage-guide.md verified against
  the published form.

## Provenance

- RAIDEN Instance installed 2026-07-08 (Edict v1.0.0). No prior ledger to
  migrate from — this is the project's first RAIDEN state record.
