# RAIDEN Instance

This directory is the local RAIDEN Instance control plane.

Read order:
1. `.raiden/state/CURRENT_STATE.md`
2. `.raiden/state/OPEN_LOOPS.md`
3. `.raiden/state/LEGACY_REVIEW.md` when present
4. `.raiden/local/README.md`
5. `.raiden/writ/README.md`

## Workspace Audit

A read-only assessment of this Instance for security, dependency health, documentation drift, and hygiene. Specification: [`.raiden/writ/WORKSPACE_AUDIT_PROTOCOL.md`](./writ/WORKSPACE_AUDIT_PROTOCOL.md).

**Invoke:** ask an agent to "run the workspace audit per the protocol in `.raiden/writ/`."

**Outputs:**
- Full report: `audit-reports/audit-YYYY-MM-DD-<short-sha>.md`
- State summary (rolling): `.raiden/state/AUDIT_LOG.md`
- State summary (latest): `.raiden/state/last-audit.md`

Cadence: ad-hoc or on rotation (typically every 2–3 months).
