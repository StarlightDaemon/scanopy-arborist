# Work Log

## 2026-07-08 — RAIDEN Instance install

- Fleet scan (RAIDEN-ops LOOP-0021) identified scanopy-arborist as an active,
  git-managed project with no RAIDEN Instance.
- Committed the one pending untracked file (`docs/usage-guide.md`) to reach a
  clean working tree.
- Created GitHub remote `StarlightDaemon/scanopy-arborist` (public), pushed
  `main`.
- Installed RAIDEN Instance at Edict v1.0.0: `.raiden/writ/` populated from
  the six-file managed payload, commit-msg hook installed, root `AGENTS.md`
  startup bridge written, D-0038 gitignore block appended.
- First-ever CI run (triggered by the install push) failed on two counts:
  `lint-and-unit` on two unused imports in `tests/unit/test_scope_audit.py`
  (fixed and pushed, commit `606f02f` — CI green for that job); `integration`
  on `test_tag_scope_canary.py`'s four-type attribution check, which
  structurally cannot pass against the CI fixture's daemon-less Scanopy
  instance. Logged as LOOP-002; bounded-task prompt written to
  `.raiden/local/prompts/ci-integration-canary-gap.md` for a future agent
  session to resolve.
- LOOP-002 resolved same day (commit `66fbc60`): bootstrapped the CI fixture
  locally (alternate port, to avoid colliding with a second live Scanopy
  instance already running) and probed the API directly rather than
  guessing. Service and DaemonApiKey are genuinely seedable and now are;
  Daemon and Discovery are structurally impossible without a live scan
  daemon (`POST /api/v1/daemons` is 405; `POST /api/v1/discovery` requires a
  `daemon_id` that fails existence-check for any non-connected daemon) and
  are now a documented, explicit exception in the canary test rather than a
  failure. CI run `28930282010` green on `main`.
