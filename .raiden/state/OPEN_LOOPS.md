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

## LOOP-002: fix CI integration canary vs. daemon-less fixture mismatch

- Status: open
- Scope: `tests/integration/test_tag_scope_canary.py::test_enumerable_types_list_with_expected_attribution`
  fails in CI because it requires live Service/Daemon/DaemonApiKey/Discovery
  instances, but `.github/scanopy-ci/docker-compose.yml` deliberately runs
  without a scan daemon. Discovered on this repo's first-ever CI run
  (2026-07-08) — not a regression from any change made this session.
- Readiness: ready. Bounded-task prompt written to
  `.raiden/local/prompts/ci-integration-canary-gap.md` — the executing agent
  should investigate Scanopy's API and choose between seeding the missing
  types in `bootstrap.sh` or scoping the canary down for daemon-less CI, per
  operator decision (do not guess without reading first).
- Closure condition: `uv run pytest tests/integration -q` passes locally
  against the CI fixture, and the CI `integration` job is green on `main`.

## Provenance

- RAIDEN Instance installed 2026-07-08 (Edict v1.0.0). No prior ledger to
  migrate from — this is the project's first RAIDEN state record.
