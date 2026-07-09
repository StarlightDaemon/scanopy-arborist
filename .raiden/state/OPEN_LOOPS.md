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

- Status: Closed 2026-07-08.
- Scope: `tests/integration/test_tag_scope_canary.py::test_enumerable_types_list_with_expected_attribution`
  failed in CI because it required live Service/Daemon/DaemonApiKey/Discovery
  instances, but `.github/scanopy-ci/docker-compose.yml` deliberately runs
  without a scan daemon. Discovered on this repo's first-ever CI run
  (2026-07-08) — not a regression from any change made that session.
- Resolution (2026-07-08, commit `66fbc60`): investigated Scanopy's API
  directly against the real CI fixture (bootstrapped locally on an alternate
  port to avoid colliding with another live Scanopy instance already running
  on 60072). Findings: **Service** and **DaemonApiKey** are genuinely
  creatable via direct API calls (`POST /api/v1/services` with
  `host_id`+`network_id`+`service_definition`+`name`; `POST /api/v1/auth/daemon`
  with `name`+`network_id`) and are now seeded inline in the test. **Daemon**
  and **Discovery** are structurally impossible to create without a live scan
  daemon — `POST /api/v1/daemons` is `405 Method Not Allowed` outright, and
  `POST /api/v1/discovery` requires a `daemon_id` that fails a server-side
  existence check (`"Daemon not found"`) for any ID that isn't an
  actually-connected daemon. Neither of the two options in the original
  bounded-task prompt applied uniformly — this was a hybrid: seed what's
  seedable, document what isn't as an expected daemon-less-CI exception
  (`_REQUIRES_LIVE_DAEMON` in the test file) rather than silently passing or
  permanently failing.
- Verified: `uv run ruff check src tests` clean, `uv run pytest tests/unit -q`
  174 passed, `uv run pytest tests/integration -q` 29 passed locally against
  the CI fixture, and CI run `28930282010` on GitHub is green (`success`) on
  `main`.
- Closure condition (met): `uv run pytest tests/integration -q` passes
  locally against the CI fixture, and the CI `integration` job is green on
  `main`.

## Provenance

- RAIDEN Instance installed 2026-07-08. No prior ledger to
  migrate from — this is the project's first RAIDEN state record.
