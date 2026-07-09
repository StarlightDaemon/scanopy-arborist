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

## 2026-07-09 — Edict v2.0.0 + state normalization

- Applied the Edict update from installed v1.0.1 to v2.0.0 (Phase D rollout,
  authorization OPS-D-002, framework loop `Raiden-ops:LOOP-F003`):
  `.raiden/writ/ROUTING_POLICY.md` added; `.raiden/writ/MODEL_TIERS.md`
  removed (managed-file-removal, expected); `README.md`, `OPERATING_RULES.md`,
  `WORKSPACE_AUDIT_PROTOCOL.md`, `FORK_REVIEW_PROTOCOL.md`, and `AGENTS.md`
  updated to the new managed content; `hooks/commit-msg` unchanged. Re-plan
  after apply confirmed "Already up to date."
- Stamped `"state_schema_version": 2` into `.raiden/instance/metadata.json`.
- Routing overlay swap: removed `.raiden/local/MODEL_MAP.md` (superseded
  tier-to-model mapping) and added `.raiden/local/ROUTING.md` (rung-based
  routing ladder, R1–R4 plus an offload pool, per the new
  `ROUTING_POLICY.md`).
- State normalization pass, per the new `OPERATING_RULES.md` Fact-Home Rule
  and Cross-Repo Citation Namespace sections:
  - `CURRENT_STATE.md`: fixed the dangling `LOOP-0021` citation (a
    Raiden-ops loop, not a local one) to the namespaced form
    `Raiden-ops:LOOP-0021` in both the Summary and Provenance sections.
  - Removed duplicate "(Edict v1.0.0)" install-narrative version mentions
    from `CURRENT_STATE.md` (Summary and Provenance), `GOALS.md`
    (Provenance), and `OPEN_LOOPS.md` (Provenance) — this was fresh-install
    narrative, not a current-version claim; the installed-Edict-version fact
    is not unique history since it is already durably recorded in this
    file's 2026-07-08 dated entry above ("Installed RAIDEN Instance at
    Edict v1.0.0") and is otherwise authoritatively tracked in
    `.raiden/instance/metadata.json`, per the Fact-Home Rule.
  - No hand-written "Last Updated"/"Last Verified" footers were found in
    any state file (`CURRENT_STATE.md`, `GOALS.md`, `OPEN_LOOPS.md`,
    `DECISIONS.md`); none to remove.
  - No loop-status restatements were found in `CURRENT_STATE.md` beyond the
    `LOOP-0021` citation above; `OPEN_LOOPS.md`'s `LOOP-001` entry is
    unchanged.
