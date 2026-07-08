# Agent Startup — RAIDEN Instance

This repo runs a RAIDEN Instance control plane in `.raiden/`.

## Read First

1. `.raiden/README.md` — control plane navigation
2. `.raiden/state/CURRENT_STATE.md` — active work and current state
3. `.raiden/state/OPEN_LOOPS.md` — pending work
4. `.raiden/writ/AGENTS.md` — full agent guide: tooling surface, write boundaries, naming canon

## Key Constraints

- **Do not write to `.raiden/writ/`** — it is RAIDEN-managed core
- **No `Co-Authored-By` in commits** — the `commit-msg` hook enforces this; do not bypass it
- **Mainline branch is `main`** — never `master`
- **D-0016**: on any Writ update — update managed core, preserve local overlay, preserve state,
  stop and report on locally modified managed files

## Naming Canon

`RAIDEN` · `Edict` · `RAIDEN Instance` · `Writ` · `payload` — use exactly; no synonyms.

## RAIDEN Tooling

Lives in the RAIDEN central repo at `/Users/dante/Citadel/Raiden/` — not in this repo.
Invoke from there with `--instance <this-repo-path>` or `--target <this-repo-path>`.
