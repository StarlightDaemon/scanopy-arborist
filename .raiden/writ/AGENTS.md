# RAIDEN Instance — Agent Guide

This file is part of the RAIDEN-managed Writ. It is the authoritative agent guide for
any repo running a RAIDEN Instance control plane. Do not edit it directly — changes
belong in the Edict package in the RAIDEN central repo.

---

## What This Repo Is

This is a **RAIDEN Instance** — a downstream repo running RAIDEN's managed control
plane in `.raiden/`. RAIDEN (the central framework repo) authors the Writ installed
here; this repo is governed by RAIDEN but owned and operated independently.

RAIDEN is not running inside this repo. All RAIDEN tooling is invoked from the central
repo against this Instance as a target.

---

## Naming Canon

Use these five terms exactly. No synonyms, no paraphrase.

| Term | Meaning |
|---|---|
| **RAIDEN** | The central framework repo and governing authority |
| **Edict** | The managed instruction/package that RAIDEN issues |
| **RAIDEN Instance** | This repo — any downstream repo with a `.raiden/` control plane |
| **Writ** | The installed managed core in `.raiden/writ/` (Edict payload after install) |
| **payload** | The installable Edict subset before install; becomes the Writ |

---

## Control Plane Read Order

Before any repo-local work, read in this order. Stop when you have what the task requires.

1. `AGENTS.md` (repo root) — entry point and key constraints
2. `.raiden/README.md` — control plane navigation index
3. `.raiden/state/CURRENT_STATE.md` — active work, deferred items, last known state
4. `.raiden/state/OPEN_LOOPS.md` — pending work and unresolved items
5. `.raiden/state/DECISIONS.md` — durable decision record for this repo
6. `.raiden/local/README.md` — local overlay index (if present)
7. `.raiden/writ/AGENTS.md` (this file) — full agent guide including tooling surface

Read only the subtree relevant to the task beyond step 2.

---

## Memory Precedence (D-0041)

The `.raiden/state/` files read above are the **system of record** for project
truth in this Instance. Native per-project memory (host- and user-scoped) holds
operator and host preferences only.

When native memory and RAIDEN's committed state disagree on any project fact,
**RAIDEN state wins.** Do not record durable project facts solely into native
memory; any project fact worth retaining is written to `.raiden/state/` in the
same pass. Native memory is invisible to other operators, hosts, and models —
committed state travels with the repo to whatever reads it next.

---

## RAIDEN Tooling — Where It Lives

RAIDEN tooling lives in the **RAIDEN central repo**, not in this repo.

The central framework path is operator-specific and is not carried in any
managed file. Per-Instance install facts live in `.raiden/instance/metadata.json`;
if your workflows need the central repo location recorded, store it in
`.raiden/local/` (overlay), not here.

Do not attempt to invoke RAIDEN tooling from within this repo.
All updater operations targeting this Instance are run from the central repo,
with this repo supplied as the `--instance` or `--target` argument.

### Installation

RAIDEN Instances are installed by a RAIDEN central agent following
`toolkit/edict/AGENT_INSTALL.md` in the central repo. The agent writes all
files directly; `plan` is the post-install verification authority.

### `raiden_updater` CLI — direct package surface

Run from `toolkit/updater/` within the RAIDEN repo:

```
python3 -m raiden_updater.cli plan  --instance <this-repo-path> --package <path>
python3 -m raiden_updater.cli apply --instance <this-repo-path> --package <path>
```

- `plan` — read-only; exits 0 if apply-safe or already current, exits 1 otherwise
- `apply` — requires an apply-safe plan; raises `ApplyError` otherwise

### Edict package location

Canonical Edict package: `toolkit/edict/package/` in the central repo.
Payload files install to `.raiden/writ/` in this Instance.

### Plan block reasons (exits 1)

| Reason | Cause |
|---|---|
| `missing_baseline` | `.raiden/writ/` has files but no `baseline.json` |
| schema incompatibility | `instance_schema_version` not in `compatible_instance_schemas` |
| `protected_path_write` | package would write into overlay or state roots |
| invalid version | version string is not strict `MAJOR.MINOR.PATCH` |
| `local_modification` | a managed file was locally modified |
| `Already up to date` | `can_apply=False` but exits **0** — not an error |

---

## Inviolable Constraints

### D-0016 — Four-Point Managed-Core Update Contract

Every Writ update must satisfy all four points:

1. Update managed core (`.raiden/writ/`)
2. Preserve local overlay (`.raiden/local/`)
3. Preserve local live state (`.raiden/state/`)
4. Stop and report if any managed file was locally modified — no silent overwrites

Conflicts surface to the operator before `apply` runs.

### Commit Attribution

- Do not add `Co-Authored-By`, `Co-authored-by`, or any agent attribution trailer lines.
- Commits carry only the operator's git identity.
- The `commit-msg` hook (installed by RAIDEN) enforces this at the git level.
- Do not remove or bypass the hook.

### Mainline Branch Naming

All RAIDEN-managed repos use `main` as the mainline branch. Never `master`.
If `git init` creates `master`, rename immediately: `git branch -m master main`.

---

## Write Boundaries

**May write:**
- Repo source files (subject to this repo's project rules)
- `.raiden/local/` — local overlay: prompts, rules, project-specific context
- `.raiden/state/` — live continuity: `CURRENT_STATE.md`, `OPEN_LOOPS.md`, `DECISIONS.md`, `WORK_LOG.md`

**Must not write:**
- `.raiden/writ/` — RAIDEN-managed core; any change requires the Edict update path
- Files in the RAIDEN central repo (unless operating as the RAIDEN agent)
- The `commit-msg` hook — do not remove, bypass, or modify it

---

## Local Prompts and Overlays

Operator-customized prompts: `.raiden/local/prompts/`

Standard prompts installed by RAIDEN:

| File | Prompt ID | Purpose |
|---|---|---|
| `instance-session-startup.md` | `raiden.instance.session-startup.v1` | Session kickoff: git status, unpushed work, operator push confirmation |
| `audit-protocol-install-handoff.md` | — | Workspace audit handoff |
| `migration-remediation.md` | — | Writ migration guidance |

Repo-specific prompts added by the operator live alongside these and are not managed.

---

## Writ Contents

Files installed by the current Writ under `.raiden/writ/`:

| File | Purpose |
|---|---|
| `README.md` | Writ managed-core index |
| `OPERATING_RULES.md` | Core operating rules, ownership boundary, Report-and-Hold, commit attribution |
| `MODEL_TIERS.md` | Capability-tier semantics referenced by the protocols |
| `WORKSPACE_AUDIT_PROTOCOL.md` | Workspace audit specification |
| `FORK_REVIEW_PROTOCOL.md` | Fork review protocol |
| `AGENTS.md` | This file — full agent guide |

---

## Workflow

- Follow the control plane read order before starting any task.
- Keep edits narrow; review the diff before committing.
- Do not edit `.raiden/writ/` files — they are managed core owned by RAIDEN.
- For Writ updates, report the required operation to the operator; the operator runs the
  updater from the central repo.
- Prefer small targeted patches over sweeping rewrites.
- If a task would cross write boundaries, stop and confirm with the operator before proceeding.
