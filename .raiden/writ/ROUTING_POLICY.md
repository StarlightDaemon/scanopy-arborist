# Routing Policy

This Edict defines how a RAIDEN Instance routes a task to a model. It replaces
the retired capability-tier scheme (`MODEL_TIERS.md`) with a single
cost/capability **ladder**. It is canonical under RAIDEN's authority order and
installs into `.raiden/writ/`.

Routing names an **order**, not a category and not a model. No file in the
managed Writ names a specific model or a specific rung's contents. The operator
maps the ladder to the models actually available to them in a local-overlay file
(`.raiden/local/ROUTING.md`), which is never managed and changes per operator and
per month — exactly the kind of detail the managed layer must not carry.

## The Ladder

The operator maintains an **ordered list of rungs**. The **top rung is the
highest capability and highest cost**; each rung below trades capability for
cost. Rung **count and contents are operator-local** — a fleet may run two rungs
or five; the managed layer fixes only the order and the rules that reference it.

A protocol that says "route to the top rung" or "any rung cleared for mechanical
work" is naming a position on the ladder; the operator resolves that position to
a concrete model at run time.

## Dispatch Rule

Route each task to the **lowest rung you would trust to do it unsupervised**.
**When in doubt, go one rung up.** The ladder has fallback built in: if a rung's
model is unavailable, the adjacent rung is the natural substitute — there is no
separate fallback designation to maintain.

## Escalation Rule

Escalate to the **top available rung** for:

- **ambiguity** — the task is under-specified or admits materially different
  correct readings;
- **conflict resolution** — reconciling competing sources, forks, or decisions;
- **security-sensitive review** — credential handling, auth/crypto, history
  rewrite, anything where being wrong is expensive;
- **Report-and-Hold dispositions** — deciding how to surface and resolve a
  Report-and-Hold condition (see `OPERATING_RULES.md`).

These are judgment-risk moments; being right outweighs being fast.

## Review Boundary

Work produced **outside the ladder** — an offload pool (other providers used for
economic reasons), another provider's output, or generated bulk output — is
**reviewed at a rung greater than or equal to the rung the task would have been
dispatched to** on the ladder. Offloading a task for cost does not lower the bar
its result must clear; it moves the judgment to the review step and pins that
step to at least the dispatch rung.

## Resolution Rule

No file in the managed Writ names a specific model. The ladder's actual rungs,
the models bound to each, the offload pool, and any billing or cost constraints
are operator-defined in `.raiden/local/ROUTING.md`. Managed files reference rung
positions ("top rung", "a rung cleared for mechanical work", "a judgment-
appropriate rung"); operators resolve those positions to models locally.
