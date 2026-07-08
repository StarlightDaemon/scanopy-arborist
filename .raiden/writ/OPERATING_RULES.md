# Writ Operating Rules

This file is a RAIDEN-managed law artifact inside an installed Writ.

## Core Rules

1. Treat files in `.raiden/writ/` as RAIDEN-managed core.
2. Put repo-specific adaptation in `.raiden/local/`, not in managed-core files.
3. Put continuity and fast-changing operational truth in `.raiden/state/`.
4. Treat local edits to managed-core files as exceptions that require explicit
   update conflict handling rather than silent overwrite.
5. Review RAIDEN updates before applying to understand scope of changes.

## Ownership Boundary

The Writ is RAIDEN-managed core; the rest of `.raiden/` is the Instance's own.

**RAIDEN-managed — the Instance agent may not write:**

- `.raiden/writ/` — the installed managed core: law and operating-rule
  artifacts, managed boundary guidance, and every other centrally owned file
  that updates as one governed unit. Changes to these files happen only through
  the Edict update path, never by in-place edit in the Instance.

**Instance-owned — the Instance agent's own surfaces:**

- `.raiden/local/` — local overlay: repo-specific prompts, rules, context, and
  exceptions.
- `.raiden/state/` — live continuity: current state, open loops, local
  decisions, work log.
- `.raiden/instance/` — install and update metadata, written by the install
  mechanism.

A local edit to a managed-core file is an exception that must be handled as an
update conflict (D-0016 point 4), not absorbed silently. Adaptation belongs in
the overlay and state layers; it must never move managed law into local notes
to dodge the boundary.

### Subagent Boundary Inheritance

Subagents inherit the role boundary of the agent that spawns them. An Instance
agent cannot elevate a subagent to Central agent scope. A subagent operating
inside a downstream repo may not write `.raiden/writ/` or any framework canon
regardless of what spawned it.

## Report-and-Hold

Report-and-Hold is the single named protocol for the three conditions under
which an agent must stop and surface a situation to the operator rather than
act through it. Each rule below is an instance of the same protocol.

- **Rule 1 — modified-managed-file conflict (D-0016 point 4):** if a managed
  file has been locally modified since install, stop — do not overwrite.
  Surface the conflict to the operator.
- **Rule 2 — dirty-tree halt:** before any distribution operation, run
  `git status` in the target Instance. If the output is non-empty, stop. Do not
  proceed into a dirty tree. Surface the dirty-tree items to the operator.
- **Rule 3 — boundary-crossing stop:** if a task would require writing to a
  surface outside the agent's role boundary (see the Ownership Boundary section
  above), stop and confirm with the operator before proceeding.

On any of the above conditions: stop, surface the issue to the operator in full
detail, take no further mutating action until the operator explicitly instructs
you to proceed.

## Commit Attribution Policy

Commits in a RAIDEN Instance must carry only the operator's git identity.

- Do not add `Co-Authored-By`, `Co-authored-by`, or any agent attribution
  trailer lines to commit messages.
- The `commit-msg` hook installed by RAIDEN enforces this at the git level.
  Do not remove or bypass it.

## Branch Naming

The mainline branch in every RAIDEN Instance must be named `main`.

- If `git init` created a `master` branch, rename it before the first RAIDEN
  install commit: `git branch -m master main`
- Do not create or leave a `master` branch as the default.
