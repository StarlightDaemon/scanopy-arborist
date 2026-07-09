# RAIDEN Local — Routing Ladder
# Local overlay. Never managed by the Edict. Update as your
# available models and billing posture change.
# Rungs ordered top-down: R1 = highest capability/cost.

## Ladder

R1 = claude-fable-5     # top rung — escalation, review boundary, Report-and-Hold dispositions
R2 = claude-opus-4-8
R3 = claude-sonnet-5
R4 = claude-haiku-4-5   # mechanical work only

## Offload pool (outside the ladder)

gemini-3.1-pro          # economic offload; output reviewed at >= the task's dispatch rung

## Billing constraints

Subscription-first: fleet agent work runs inside the operator's existing
subscription; separate metered API billing is avoided. Fleet-level economic
policy: Raiden-ops state/DECISIONS.md OPS-D-003.
