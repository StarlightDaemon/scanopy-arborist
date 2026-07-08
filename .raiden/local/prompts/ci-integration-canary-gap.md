# CI Integration Canary Gap — Bounded Task

## Prompt ID

`scanopy-arborist.local.ci-canary-gap.v1`

## Purpose

Resolve a design mismatch between `tests/integration/test_tag_scope_canary.py`
and the CI Scanopy fixture, discovered on this repo's first-ever CI run
(2026-07-08, after the GitHub remote was created).

## Context (read first)

- `.github/workflows/ci.yml` — the `integration` job
- `.github/scanopy-ci/docker-compose.yml` — note its own comment: "The scan
  daemon is deliberately omitted: the integration suite creates its own
  manual hosts and never depends on live discovery."
- `.github/scanopy-ci/bootstrap.sh` — current seed step (org/network/API key
  only)
- `tests/integration/test_tag_scope_canary.py` — specifically
  `test_enumerable_types_list_with_expected_attribution`

## Template

```text
You are working inside the current repo (scanopy-arborist) as a bounded
execution agent.

Task:
- CI's `integration` job fails on
  `test_tag_scope_canary.py::test_enumerable_types_list_with_expected_attribution`.
  The test asserts that four Scanopy resource types — Service, Daemon,
  DaemonApiKey, Discovery — each have at least one live instance on the test
  server, so it can verify their attribution field. The CI Scanopy fixture
  (`.github/scanopy-ci/docker-compose.yml`) deliberately runs without a scan
  daemon, so those four types can never have instances there. This is a
  first-run discovery, not a regression — the repo had no GitHub remote (and
  therefore no CI) until 2026-07-08, so this canary (authored 2026-07-07,
  commit 075772b) was validated by hand against a real Scanopy instance with
  a daemon attached, never against this daemon-less CI fixture.

Required outcome:
- Investigate how Service/Daemon/DaemonApiKey/Discovery records are created
  in Scanopy's API (read the Scanopy API docs/OpenAPI spec, or the server
  source if vendored/available) and choose between:
  (a) extending `.github/scanopy-ci/bootstrap.sh` to seed one instance of
      each missing type via direct API calls, matching the pattern it
      already uses for org/network/API key creation, or
  (b) scoping `test_enumerable_types_list_with_expected_attribution` down so
      it skips (not silently passes) verification for types that structurally
      cannot exist without a live daemon, with a clear comment explaining why,
      and relying on manual/live verification (the "(live)" runs already
      documented in `docs/usage-guide.md`) for those types instead.
  Pick whichever is actually correct given how Scanopy's API works — don't
  guess; read before choosing. If neither cleanly applies, report back with
  findings rather than forcing one.
- Whichever path is chosen, `uv run pytest tests/integration -q` must pass
  locally against the same disposable Scanopy fixture CI uses
  (`docker compose -f .github/scanopy-ci/docker-compose.yml up -d --wait` +
  `bash .github/scanopy-ci/bootstrap.sh`), and the CI `integration` job must
  go green on push.

Constraints:
- Do not weaken the canary's actual purpose (catching tag-reach drift after a
  Scanopy upgrade) — only resolve the daemon-less-environment mismatch for
  the four affected types.
- Do not touch the `lint-and-unit` job or `tests/unit/` — already green.
- Do not pick up LOOP-001 (OWNER placeholder / v0.1.0 release cut) — that is
  explicitly out of scope for this task; leave it in `OPEN_LOOPS.md`
  untouched.
- Push directly to `main` once CI is confirmed green — no branch-protection
  gate on this repo currently, and this matches how install/setup work has
  been done on this repo so far this week.
- Commits must carry no `Co-Authored-By` or agent-attribution trailers (the
  installed `commit-msg` hook enforces this and will reject the commit).

Working rules:
- read only the files needed for this task
- do not broaden scope without evidence
- report blockers clearly
- preserve existing authority and naming unless the task requires a change

Finish by reporting:
- what changed (bootstrap.sh seed additions, or canary test scoping — with
  rationale for whichever was chosen)
- what was verified (local integration run output, CI run link/conclusion)
- any blocker or follow-up still open
- update this repo's `.raiden/state/WORK_LOG.md` with a dated entry and close
  LOOP-002 in `.raiden/state/OPEN_LOOPS.md`
```

## Notes

- Written 2026-07-08 by the RAIDEN central agent, following operator
  decisions recorded in RAIDEN-ops (LOOP-0021 follow-on: operator chose
  "let the agent investigate and propose," "push directly once tests pass,"
  and "CI fix only, do not bundle LOOP-001").
- Based on `bounded-task-template.md` (`toolkit/prompts/`).
