# Model Tiers

This Edict defines the capability tiers that RAIDEN protocols reference when a
task should be routed to a model with particular strengths. It is canonical
under RAIDEN's authority order and installs into `.raiden/writ/`.

Tiers name *capabilities*, not models. No file in the managed Writ names a
specific model. Each operator maps these tiers to the models actually available
to them in a local-overlay file (`.raiden/local/MODEL_MAP.md`), which is never
managed and changes per operator and per month — exactly the kind of detail the
managed layer must not carry.

A protocol that says "route to TIER_DEEP_REASONING" is telling the operator's
local mapping which capability the task needs; the operator resolves that tier
to a concrete model at run time.

## Tiers

### TIER_DEEP_REASONING

- **Purpose:** tasks requiring extended analysis, multi-step inference,
  architectural decisions, or synthesis across many inputs.
- **Capability:** use when correctness matters more than speed and the task
  benefits from the model thinking through competing interpretations before
  acting. This is the tier for judgment-heavy work — security review, conflict
  resolution, speculative triage, and any decision where being right outweighs
  being fast.

### TIER_FAST_EXECUTION

- **Purpose:** mechanical, well-specified, deterministic tasks — file
  operations, path updates, format conversions, scripted sequences where the
  correct action is unambiguous.
- **Capability:** use when speed matters and the task requires execution rather
  than judgment. There is one correct output and the model's job is to produce
  it quickly, not to deliberate over alternatives.

### TIER_LONG_CONTEXT_REVIEW

- **Purpose:** tasks that require holding a large body of content in context
  simultaneously — whole-repo audits, cross-file analysis, large document
  review.
- **Capability:** use when the task cannot be meaningfully chunked without
  losing coherence across the full context. The defining need is breadth of
  simultaneous context, not depth of reasoning on any single point.

### TIER_FALLBACK

- **Purpose:** the operator's designated default model for tasks that do not
  clearly require a specialized tier, or when the primary tier model is
  unavailable.
- **Capability:** use for general-purpose, bounded work that needs competent
  judgment but neither extended reasoning, raw execution speed, nor a large
  context window. Every operator must define a FALLBACK mapping; it is the
  safety net the other tiers fall back to.

## Resolution Rule

No file in the managed Writ names a specific model. Tier-to-model mapping is
operator-defined in `.raiden/local/MODEL_MAP.md`. Managed files reference
tiers; operators resolve tiers to models locally.
