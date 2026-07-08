# Writ Managed Core

This is the installed managed-core payload of the Edict package (v1.0.1).

In a downstream RAIDEN Instance it installs to `.raiden/writ/`. Every file here
is RAIDEN-managed core: authored centrally, versioned and hash-tracked as one
unit, and updated only through the Edict update path — never edited in place in
an Instance.

## Contents

Six managed files plus one git hook:

| File | Purpose |
|---|---|
| `AGENTS.md` | Full agent guide: naming canon, control-plane read order, memory precedence (D-0041), tooling surface, write boundaries, Writ contents |
| `OPERATING_RULES.md` | Core operating rules, ownership boundary, Report-and-Hold protocol, commit attribution, branch naming |
| `MODEL_TIERS.md` | Capability-tier semantics (TIER_DEEP_REASONING, TIER_FAST_EXECUTION, TIER_LONG_CONTEXT_REVIEW, TIER_FALLBACK); names no models |
| `WORKSPACE_AUDIT_PROTOCOL.md` | Canonical read-only workspace audit specification; routes by capability tier |
| `FORK_REVIEW_PROTOCOL.md` | Canonical fork-review specification; routes by capability tier |
| `README.md` | This file — Writ managed-core index |
| `hooks/commit-msg` | Git-level enforcement of the commit-attribution policy; installs to `.git/hooks/commit-msg` |

## Conventions in This Payload

- **No named models.** Protocols reference capability tiers defined in
  `MODEL_TIERS.md`. The tier→model mapping is operator-defined in the local
  overlay (`.raiden/local/MODEL_MAP.md`), never in managed files.
- **No machine-absolute paths.** Per-Instance install facts live in
  `.raiden/instance/metadata.json`; operator-specific locations live in the
  local overlay.

The installed `Writ` version always equals `manifest.json`'s `edict_version`.
