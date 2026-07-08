# Fork Review Protocol

This Edict defines the canonical fork review process for a RAIDEN Instance. It is the authoritative specification of fork analysis scope, attribution tracking, synthesis routing, output structure, and state publication. Any agent invoked to perform a fork review follows this protocol exactly.

## Purpose

The fork review is a read-only comparative analysis of one or more forked source files against a designated baseline source. It evaluates:

- What each fork added, removed, or modified relative to the baseline
- Change-level attribution — which author introduced which change
- Feature surface across all forks — overlaps, unique contributions, conflicts
- Code quality signals — improvements, regressions, dead code, introduced bugs
- Synthesis candidates — changes worth carrying forward into a successor
- Cross-fork conflicts and incompatibilities
- Open observations (a deliberately curious speculative pass)

The review produces a per-fork Markdown report and a cross-fork synthesis report inside the Instance, and publishes a summary into the Instance's state layer.

## Authority

This Edict is canonical under RAIDEN's authority order. It is installed into `.raiden/writ/` by the updater. Per-Instance local overrides are NOT honored for this protocol — Instances may add fork-review-related local prompts under `.raiden/local/prompts/` for invocation convenience, but the protocol body itself is sourced from this file.

## Companion Canon

- `toolkit/prompts/handoff-template.md` — structural model for synthesis seeds (see Synthesis Routing below). Each synthesis candidate's seed is a bounded-task handoff from the review agent to a downstream implementation agent.
- `toolkit/prompts/completion-template.md` — structural model for state-publication closeout (see Output).
- `WORKSPACE_AUDIT_PROTOCOL.md` — sibling edict for repository health auditing. Fork review is a distinct domain (comparative code analysis and attribution) and is not a substitute for nor a duplicate of the workspace audit.

## Model Expectation

The fork review requires a model capable of precise diff reasoning, change-level attribution across multiple files, cross-fork synthesis judgment, and a speculative observations pass. Route to **TIER_DEEP_REASONING** (see `MODEL_TIERS.md`); if that tier's model is unavailable, fall back to **TIER_FALLBACK**.

Per-Instance routing config may override this preference; see Synthesis Routing for routing-config lookup. Tiers resolve to concrete models through the operator's local mapping (`.raiden/local/MODEL_MAP.md`).

## Hard Constraints

- All source files under review are read-only. No commits, pushes, tags, stashes, branch operations, or any modification to fork source files, the baseline file, or any other source file.
- No mutating commands of any kind against source files.
- Permitted operations: read (`cat`, `head`, `less`), search (`grep`, `rg`, `find`, `ls`), diff (`diff`, `git diff`), and structural inspection only.
- Permitted writes: per-fork report files, the cross-fork synthesis report, and the state-publication files (paths defined under Output). No other writes anywhere in the Instance.
- Do NOT modify `CURRENT_STATE.md`, `OPEN_LOOPS.md`, or `DECISIONS.md`. Operator curation owns those.

## Scope

- The baseline file is the designated original source. It is the immutable comparison anchor for all forks. It is never treated as a fork candidate and never appears as a finding subject. Its path will be specified at invocation or identified by the `og_` prefix convention in `/forks/`.
- Each fork is analyzed individually against the baseline, then collectively against each other.
- Read RAIDEN orientation in order: `AGENTS.md` → `.raiden/README.md` → `.raiden/state/CURRENT_STATE.md` → `.raiden/state/OPEN_LOOPS.md`. These are authoritative for the Instance's structure, conventions, and current state.
- Read `/forks/MANIFEST.md` as the authoritative inventory of forks to review. Any file flagged in the manifest as having an unknown author or unresolved conflict is noted in each relevant report section; the review proceeds but flags carry through.
- Locate scoped model-routing config if present (`.raiden/routing.md`, `.raiden/models.md`, `.raiden/agents.md`, or a routing section in `RAIDEN.md`). If found, it is authoritative for the Recommended model field on each synthesis candidate.

## Review Categories

### 1. Baseline Identification

Read and characterize the baseline file before any fork analysis begins. Record:

- File path and filename
- Author, mod name, and version as declared in the file header
- Declared feature set (from header comments, settings schema, or documentation blocks)
- Approximate line count and structural sections (settings, globals, hooks, helpers, UI)
- Any known issues or TODOs noted in the baseline itself

This section is produced once and shared across all per-fork reports by reference. It is reproduced in full in the cross-fork synthesis report.

### 2. Per-Fork Diff Analysis

For each fork, produce a structured diff against the baseline covering:

- **Additions** — new functions, new settings, new logic blocks, new constants, new includes
- **Subtractions** — removed functions, removed settings, removed logic, removed includes
- **Modifications** — changed function bodies, changed settings schema, changed constants, changed behavior

For each changed unit (function, setting, block), record:
- Unit name / identifier
- Change type (addition / subtraction / modification)
- Line range in the fork file
- Brief description of what changed and apparent intent

Do not summarize wholesale. Every discrete change gets its own entry. Small whitespace-only or comment-only changes may be grouped if they carry no behavioral difference; note the grouping explicitly.

### 3. Change-Level Attribution

For every change identified in Category 2, record the attributed author. Attribution is taken from:

1. The fork file's declared `@author` or equivalent header field (primary)
2. The fork's MANIFEST.md entry (secondary, if header is absent or ambiguous)
3. The subfolder author segment in `/forks/{author}/` (tertiary fallback)

If a fork contains changes that themselves credit a secondary contributor (e.g. a fork of a fork, or inline attribution comments), record both the fork author and the credited secondary contributor separately. Do not flatten multi-layer attribution.

Attribution is recorded per change entry in the per-fork report and aggregated into an Attribution Index in the cross-fork synthesis report.

### 4. Feature Surface Comparison

Across all forks, map the complete feature surface as a table with one column per fork plus the baseline:

- List every distinct feature or capability as a row
- Mark each cell: present (✓), absent (–), modified variant (△), or removed (✗)
- Flag features that appear in multiple forks with different implementations
- Flag features that appear in only one fork (unique contributions)
- Flag features present in the baseline that have been removed in one or more forks

Produce this matrix in the cross-fork synthesis report.

### 5. Code Quality Signals

For each fork, assess the changes against the baseline for:

- **Improvements** — cleaner logic, better error handling, more robust edge-case coverage, reduced redundancy
- **Regressions** — introduced bugs, removed safety checks, broken logic paths, narrowed compatibility
- **Dead code** — additions that are unreachable or unused
- **Style drift** — significant deviation from the baseline's coding conventions that would complicate merging
- **Compatibility signals** — changes that expand platform/runtime compatibility vs. changes that narrow it

Quality signals are observations, not verdicts. Label each as Positive, Negative, or Neutral. Do not editorialize beyond what the code supports.

### 6. Synthesis Candidates

Enumerate every change across all forks that is a candidate for inclusion in a successor implementation. A change is a synthesis candidate if it:

- Adds or improves functionality not present or not working correctly in the baseline
- Does not directly conflict with another higher-ranked candidate
- Is self-contained enough to be ported without carrying the entire fork

For each candidate:

- Assign a recommendation signal: **Recommended** (clear improvement, low integration risk), **Consider** (worthwhile but requires judgment or has integration complexity), or **Flag** (surfaced for operator awareness, not recommended without further review)
- Record the source fork and attributed author
- Write a one-to-two sentence synthesis seed describing what a downstream implementation prompt would need to do to incorporate this change (scope, target location, success criterion, attribution requirement)

The agent recommends; the operator decides. List all candidates regardless of signal. Do not filter or suppress Flag-level candidates.

### 7. Cross-Fork Conflicts and Incompatibilities

Identify changes across forks that directly contradict each other — different implementations of the same function, conflicting settings schema changes, incompatible behavioral modifications. For each conflict:

- Name the conflicting forks and the specific units in conflict
- Describe the nature of the conflict
- Note which approach (if any) is more consistent with the baseline's apparent design intent
- Flag as requiring operator decision before synthesis can proceed

### 8. Open Observations (Speculative Pass)

A deliberately curious pass across all forks and the baseline: surface anything that looks off, surprising, or worth a second look — naming inconsistencies, orphaned code, patterns that suggest a fork author misunderstood the baseline, build or config oddities, anything that pattern-matches as "huh, that's strange."

Findings default to Info unless they cross another category's threshold. Prefix uncertain observations with `(speculative)`.

## Significance Scheme

- **Critical** — introduced security issue (hardcoded credential, unsafe string handling in a privileged context, etc.); breaking regression that would prevent the mod from functioning
- **High** — significant behavioral regression; removal of a feature present in the baseline without apparent justification; conflict between forks that blocks synthesis of high-value changes
- **Medium** — meaningful code quality issue; style drift severe enough to complicate merging; unresolved multi-layer attribution
- **Low** — minor hygiene, cosmetic changes, trivial dead code
- **Info** — observations, positive signals, speculative notes

## Synthesis Routing

Every synthesis candidate is tagged with routing metadata for downstream prompt building.

### Step 1: Apply scoped routing config if found

If a scoped routing config exists (`.raiden/routing.md`, `.raiden/models.md`, `.raiden/agents.md`, or a routing section in `RAIDEN.md`), its assignments are authoritative for the Recommended model field. Use them verbatim where they cover the change type.

### Step 2: For candidates not covered by scoped config, classify by class

| Class | Description | Default capability tier |
|---|---|---|
| MECHANICAL | Direct port of a self-contained change with no judgment required (new constant, settings field, isolated helper) | TIER_FAST_EXECUTION |
| TARGETED-PORT | Bounded change in 1–2 functions requiring light adaptation (behavioral tweak, patched logic) | TIER_FALLBACK |
| MULTI-UNIT-INTEGRATION | Coordinated changes across multiple functions or structural areas | TIER_LONG_CONTEXT_REVIEW |
| CONFLICT-RESOLUTION | Requires operator-informed judgment to resolve competing fork implementations before porting | TIER_DEEP_REASONING |
| SPECULATIVE-TRIAGE | First decide whether the change is worth porting; two-stage (triage → class-appropriate port if confirmed) | TIER_DEEP_REASONING |

Tiers are defined in `MODEL_TIERS.md` and resolved to concrete models through the operator's local mapping (`.raiden/local/MODEL_MAP.md`). When in doubt between two classes, the more cautious class wins — prefer TIER_DEEP_REASONING over TIER_FALLBACK, and TIER_FALLBACK over TIER_FAST_EXECUTION.

### Step 3: Write a synthesis seed

For each synthesis candidate, write a 1–2 sentence seed describing what a downstream implementation prompt would need to accomplish. The seed contains: source fork, attributed author, target location in a successor file, scope of change, success criterion, and attribution requirement. See `toolkit/prompts/handoff-template.md` for the canonical handoff shape.

## Process

1. Read RAIDEN Instance orientation files in order.
2. Read `/forks/MANIFEST.md` as the authoritative fork inventory.
3. Locate and characterize the baseline file (Category 1).
4. Locate scoped model-routing config if present.
5. For each fork listed in the manifest, execute Categories 2–3 (per-fork diff and attribution).
6. Execute Categories 4–8 across all forks collectively.
7. Assign significance levels; tag all synthesis candidates with class, model, and seed.
8. Write per-fork reports (paths below).
9. Write cross-fork synthesis report (path below).
10. Publish state summary (paths below).

## Output

### Per-Fork Reports — Filename

Write one Markdown report per fork at:

```
fork-reports/fork-review-{author-kebab}-{fork-name-kebab}-{YYYY-MM-DD}.md
```

Where `{author-kebab}` and `{fork-name-kebab}` match the directory segments used in `/forks/MANIFEST.md`, and `YYYY-MM-DD` is the current local date when the review runs.

**Collision handling:** if a file with this exact name already exists, append `-HHMMSS` before `.md`.

Create the `fork-reports/` directory if absent.

### Per-Fork Report — Required Sections

- **Header** — fork name, author, source file path, baseline file path, review date
- **Baseline Reference** — one-line pointer to the Baseline Identification section in the synthesis report
- **Diff Analysis** — per-change entries (Category 2), organized by change type
- **Attribution** — per-change attribution table (Category 3)
- **Code Quality Signals** — per-signal entries (Category 5), labeled Positive / Negative / Neutral
- **Synthesis Candidates from this fork** — candidates sourced from this fork only, with signal, class, model, and seed
- **Flags** — any manifest flags, missing attribution, or anomalies carried from MANIFEST.md
- **Appendix** — tools used, approximate line counts, any skips with justification

### Cross-Fork Synthesis Report — Filename

Write one Markdown report at:

```
fork-reports/synthesis-{YYYY-MM-DD}.md
```

**Collision handling:** same `-HHMMSS` suffix rule as per-fork reports.

### Cross-Fork Synthesis Report — Required Sections

- **Executive Summary** — baseline identified, forks reviewed (count and list), total synthesis candidates by signal, top 3 priorities
- **Baseline Identification** — full baseline characterization (Category 1)
- **Feature Surface Matrix** — full cross-fork feature table (Category 4)
- **Attribution Index** — all authors across all forks, changes attributed to each, any multi-layer attribution noted
- **All Synthesis Candidates** — complete list across all forks, grouped by recommendation signal (Recommended → Consider → Flag), ordered by significance within group; each entry includes source fork, author, class, recommended model, and synthesis seed
- **Conflicts and Incompatibilities** — all cross-fork conflicts (Category 7) with operator decision required flags
- **Open Observations** — speculative pass findings (Category 8)
- **Remediation Plan** — synthesis candidates grouped by class, ordered significance-then-fork within class, with model assignment per class
- **Appendix** — forks reviewed (with paths), baseline path, routing source, any skips

### State Publication

After all reports are written, the review agent publishes two state files. Both reference the exact filenames of the reports just written.

**1. `.raiden/state/FORK_REVIEW_LOG.md` (rolling, append-only)** — prepend a new entry to the top of the entries section:

```
## YYYY-MM-DD — {baseline filename}

- Forks reviewed: N
- Synthesis candidates: Recommended N | Consider N | Flag N
- Significance: Critical N | High N | Medium N | Low N | Info N
- Per-fork reports: fork-reports/fork-review-*.md (N files)
- Synthesis report: fork-reports/synthesis-YYYY-MM-DD[-HHMMSS].md
- Top priority: <one-line summary of #1 synthesis priority>
```

If `FORK_REVIEW_LOG.md` doesn't exist, create it with a brief header and the first entry.

**2. `.raiden/state/last-fork-review.md` (latest-only, overwritten)** — replace contents with:

```
# Last Fork Review

- Date: YYYY-MM-DD
- Baseline: {filename}
- Forks reviewed: N
- Synthesis report: fork-reports/synthesis-YYYY-MM-DD[-HHMMSS].md
- Candidates: Recommended N | Consider N | Flag N
- Top 3 priorities:
  1. <one-line>
  2. <one-line>
  3. <one-line>
```

## Reporting Discipline

- Every change entry cites a file path and line range.
- Attribution is always taken from the file itself first. Never invent or assume an author.
- Zero changes in a category is a valid result. Write "No findings." and move on. Do not pad.
- Confidence labels: prefix uncertain observations with `(low-confidence)` or `(speculative)`.
- No synthesis execution. Candidates and seeds only — implementation is downstream.
- Synthesis routing fields only on actionable candidates.
- Use class defaults verbatim when scoped routing doesn't cover a candidate. Do not invent novel model assignments.
- Redact any accidentally committed secrets found in fork files per the zero-tolerance rule in `WORKSPACE_AUDIT_PROTOCOL.md` — flag as Critical and halt synthesis candidates for the affected fork pending operator review.
