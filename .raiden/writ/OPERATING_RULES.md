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

## Fact-Home Rule

Every durable fact has **exactly one authoritative surface**. Every other
surface may **reference** it — by pointer or ID — but must **not restate its
value**. A fact that lives in one place cannot disagree with itself; the moment
a fact is copied into prose in a second place, one copy starts to rot and
nothing measures which. This is the same discipline the Writ applies to law
(one hashed source of truth), applied to state.

Authoritative homes inside an Instance:

| Fact | Authoritative home | Everything else does |
|---|---|---|
| Installed Edict version | `.raiden/instance/metadata.json` | never restated in state prose |
| Writ composition | manifest + baseline | never listed in state prose |
| Loop status | `.raiden/state/OPEN_LOOPS.md` entry | `CURRENT_STATE.md` cites `LOOP-xxx` without restating open/closed |
| Decisions | `.raiden/state/DECISIONS.md` | cited by ID, never re-summarized as if authoritative |
| When a file was last true | git history of that file | **no hand-written "Last Updated" / "Last Verified" date footers** |
| Volatile counts (tests, commits, components) | the repo itself | stated in prose only inside dated `WORK_LOG.md` entries, never in `CURRENT_STATE.md` |
| Fleet roster / versions / lifecycle | the ops registry (private ops repo) | cited across repos via the citation namespace below, never re-tallied in an Instance |

Corollaries:

- Do **not** write the installed Edict version into `CURRENT_STATE.md` or any
  other state prose. Read it from `metadata.json`.
- Do **not** restate a loop's open/closed status where the loop is cited; the
  citation carries the reader to the authoritative entry.
- Volatile counts belong in a **dated** `WORK_LOG.md` entry (a snapshot with a
  date is a historical record, not a current-state claim); they do not belong in
  `CURRENT_STATE.md`, where they are stale the moment work continues.
- Retire hand-maintained "Last Updated" footers. Freshness is derived from git,
  which already records exactly when a file was last true; a footer that lies is
  worse than no footer.

## One Writer Per Repo

At most **one agent session writes a given repo at a time.** Parallel work fans
out **across** repos, not **within** one. Two sessions mutating the same repo
race on non-atomic multi-file writes and silently clobber each other's state;
the safe unit of concurrency is the repository, not the file. When more work is
available than one session can carry, dispatch additional sessions to *other*
repos rather than a second session into the same one.

## Cross-Repo Citation Namespace

References to another repo's work items use the form
**`<RegistryName>:LOOP-xxx`** and **`<RegistryName>:D-xxx`**, where
`<RegistryName>` is that Instance's name in the ops registry. The registry name
is the namespace; each Instance keeps its own local `LOOP-`/`D-` sequence.
Renumbering every repo's history into one global sequence would be pure churn —
the ambiguity only ever hurts at the **citation site**, and a namespace prefix
resolves it there. A bare `LOOP-004` means "this repo's LOOP-004"; another
repo's is `Atlas:LOOP-004`.

## Root CLAUDE.md Is a Pointer Only

In a RAIDEN Instance, the repo-root `CLAUDE.md` is a **pointer only** — at most
three lines directing the reader to `AGENTS.md`. It carries **no substantive
governance**. Two auto-loaded surfaces with independent substantive content is
how an Instance ends up governed by two things that disagree (the fact-home rule
applied to instructions). Substantive local governance lives in
`.raiden/local/rules/` (or in the root `AGENTS.md` bridge itself when short),
where it survives updates and sits inside the inventoried overlay boundary.
