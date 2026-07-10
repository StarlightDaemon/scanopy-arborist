# Open Loops

Work must be executed one loop at a time.

## LOOP-001: publish the repo (fill in `OWNER`, cut v0.1.0)

- Status: Closed (2026-07-09)
- Gate: operator
- Scope: replace the `OWNER` placeholder across `pyproject.toml`,
  `deploy/docker/docker-compose.yml`, `deploy/podman/arborist.container`,
  `deploy/lxc/`, and the README/docs with `starlightdaemon` (now that the
  GitHub remote exists), then run the `RELEASE.md` sequence to cut `v0.1.0`.
- Readiness: ready — GitHub remote now exists
  (`StarlightDaemon/scanopy-arborist`), which was the blocking precondition.
- Closure condition: `OWNER` placeholder fully resolved, `v0.1.0` tagged and
  pushed, install instructions in README/docs/usage-guide.md verified against
  the published form.
- Resolution (2026-07-09): `OWNER` replaced with `StarlightDaemon` (GitHub
  URLs) / `starlightdaemon` (lowercase GHCR image refs) across 9 files — 31
  occurrences total: `README.md` (6), `docs/usage-guide.md` (12),
  `pyproject.toml` (1), `deploy/docker/docker-compose.yml` (1),
  `deploy/podman/arborist.container` (1), `deploy/podman/README.md` (1),
  `deploy/lxc/ct/arborist.sh` (4), `deploy/lxc/install/arborist-install.sh`
  (3), `deploy/lxc/README.md` (2). Also updated `CURRENT_STATE.md`/
  `GOALS.md` state to reflect the publish (no `OWNER` literal remains in
  either). `git grep -c OWNER` is 11 afterward, all legitimate: this file's
  own loop record, `GOALS.md`'s "Done" milestone description, and
  `RELEASE.md`/`docs/verification-real-vm.md`/
  `.raiden/local/prompts/ci-integration-canary-gap.md` referring to the
  concept/history rather than an unresolved placeholder. Also found and
  fixed a pre-existing bug while doing this: every install/clone/raw-fetch
  URL was written against
  `scanopy-arborist-mcp` as the repo name, but the actual GitHub remote is
  `scanopy-arborist` (no `-mcp` suffix) — those URLs would have 404'd even
  with `OWNER` filled in. Fixed throughout (README, RELEASE.md, usage-guide,
  the three LXC references, pyproject.toml `Homepage`); left
  `scanopy-arborist-mcp` as-is where it's a distinct namespace, not a broken
  link (the PyPI/package `name` in `pyproject.toml`, and the GHCR image name).
  Bumped version from the stale `0.1.0b1` beta suffix to `0.1.0` in
  `pyproject.toml` and `src/arborist/__init__.py` to match the tag (`arborist
  --version` now prints `arborist 0.1.0`). Merged the `CHANGELOG.md`
  "Unreleased" scope-confinement-audit section into the `v0.1.0` entry since
  both ship together in this first tag. `uv run ruff check src tests` clean;
  `uv run pytest tests/unit -q` 174 passed. Tagged `v0.1.0` (annotated) and
  published the GitHub release; see `WORK_LOG.md` for commit/tag SHAs and the
  release URL.

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
