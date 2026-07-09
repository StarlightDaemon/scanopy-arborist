# Workspace Audit Protocol

This Edict defines the canonical workspace audit for a RAIDEN Instance. It is the authoritative specification of audit scope, severity, remediation routing, output, and state publication. Any agent invoked to perform a workspace audit follows this protocol exactly.

## Purpose

The workspace audit is a read-only assessment of a single RAIDEN Instance's repository, evaluating:

- Exposed secrets and credentials (zero-tolerance)
- Dependency vulnerabilities (production and development reported separately)
- Outdated dependencies and deprecated APIs
- Documentation drift
- Repository hygiene
- Configuration risk
- License and legal compliance
- Open observations (a deliberately curious speculative pass)

The audit produces a Markdown report inside the Instance with per-finding remediation routing for downstream prompt building, and publishes a summary into the Instance's state layer.

## Authority

This Edict is canonical under RAIDEN's authority order. It is installed into `.raiden/writ/` by the updater. Per-Instance local overrides are NOT honored for this protocol — Instances may add audit-related local prompts under `.raiden/local/prompts/` for invocation convenience, but the protocol body itself is sourced from this file.

## Companion canon

- `toolkit/prompts/read-only-audit-review-template.md` — operator-invoked governance/structural review. Run as a milestone-level companion to the technical audit, not as a substitute. Different domain (governance coherence) and audience (operator/reviewer).
- `toolkit/prompts/handoff-template.md` — structural model for remediation seeds (see Remediation Routing below). Each actionable finding's seed is functionally a bounded-task handoff from the audit agent to a downstream remediation agent.
- `toolkit/prompts/completion-template.md` — structural model for state-publication closeout (see Output).

## Model expectation

The audit requires a model capable of severity judgment, Raiden-doc cross-referencing, and a speculative observations pass. Route to **the top available rung** (see `ROUTING_POLICY.md`); if the top rung's model is unavailable, the adjacent rung is the natural substitute per the ladder's built-in fallback.

Per-Instance routing config may override this preference; see Remediation Routing for routing-config lookup. Rungs resolve to concrete models through the operator's local mapping (`.raiden/local/ROUTING.md`).

## Hard Constraints

- The repository under audit is read-only. No commits, pushes, tags, stashes, branch operations, or any modification to source files, dependencies, configurations, lockfiles, or git state.
- No mutating commands. No installers, upgraders, formatters, auto-fix linters, codemods, migrations.
- Permitted commands: read (`cat`, `head`, `less`), search (`grep`, `rg`, `find`, `ls`), git inspection (`git log`, `git diff`, `git show`, `git ls-files`, `git blame`, `git status`), and read-only audit subcommands (`npm audit`, `pnpm audit`, `pip-audit`, `cargo audit`, `govulncheck`, `bundle audit check --update=false`, `gitleaks detect --no-git --redact`, `trufflehog filesystem . --no-update`).
- Mutating checks are skipped, not adapted; record the skip in the report appendix.
- Permitted writes: the audit report file and the state-publication files (paths under Output). No other writes anywhere in the Instance.

## Scope

- Audit only the current repository.
- Audit the HEAD commit of the current branch. Uncommitted working-tree changes are environment state, not audit findings; they appear in the Appendix only if genuinely security-relevant.
- Cover tracked files at HEAD plus a sample of git history (for secret detection).
- Polyglot: auto-detect ecosystems present (Node, Python, Go, Rust, Ruby, Java/JVM, .NET, PHP, etc.). Skip cleanly when an ecosystem is absent.
- Read the target's canonical orientation. For RAIDEN Instances: `AGENTS.md` → `.raiden/README.md` → `.raiden/state/CURRENT_STATE.md` → `.raiden/state/OPEN_LOOPS.md`. For framework repos or other non-Instance targets without a `.raiden/` layer: read the root-level canonical docs that exist (typically `README.md`, governance docs like `GOVERNANCE.md` or `REPOSITORY_MAP.md`, and any present state files like `CURRENT_STATE.md`, `OPEN_LOOPS.md`, `DECISIONS.md`).
- Locate scoped model-routing config if present. Search `.raiden/local/ROUTING.md` (the canonical routing overlay), then `.raiden/routing.md`, `.raiden/models.md`, `.raiden/agents.md`, a routing section in a separate `RAIDEN.md`, or — for framework repos and non-Instance targets — root-level equivalents like `routing.md`, `models.md`, or routing sections in canonical governance docs. If found, it is authoritative for the Recommended model field on each actionable finding. If absent everywhere, fall back to the class defaults in Remediation Routing.

## Audit Categories

### 1. Exposed Secrets

Run a secrets scanner if available (`gitleaks`, `trufflehog`). Otherwise, pattern-search the working tree AND `git log -p` for: cloud provider credentials (AWS `AKIA*`/`ASIA*`, GCP service-account JSON, Azure connection strings); common SaaS tokens (Stripe `sk_live_*`, GitHub `ghp_*`/`github_pat_*`, Slack `xox*`, OpenAI `sk-*`, Anthropic `sk-ant-*`); committed credential files (`.env*`, `*.pem`, `id_rsa`, `*.keystore`, `credentials.json`, `service-account*.json`).

Verify `.gitignore` excludes typical secret-bearing paths. Flag any secret in git history even if removed from the current tree.

**Zero-tolerance rule:** any secret, credential, or API key found in the working tree or git history is reported as Critical regardless of whether it appears live, revoked, expired, or placeholder-like. No exceptions, no downgrades.

### 2. Dependency Vulnerabilities

For each detected ecosystem, run its native read-only audit:
- Node: `npm audit --json` / `pnpm audit --json` / `yarn npm audit --json`
- Python: `pip-audit` or `safety check`
- Rust: `cargo audit`
- Go: `govulncheck ./...`
- Ruby: `bundle audit check --update=false`
- PHP: `composer audit`

Report CVEs by severity, package, installed version, and fixed-in version.

**Report production and development dependencies separately.** Lead this category with the explicit split:

> Production dependencies: N findings. Development dependencies: N findings.

A clean production tree MUST be affirmatively stated, never implied by absence.

### 3. Outdated Dependencies & Deprecated APIs

- Packages >1 major version behind or >12 months stale.
- APIs explicitly deprecated in the targeted runtime/framework version.
- Runtime pins (Node, Python, Ruby, etc.) that are EOL or in extended-support-only status.

### 4. Documentation Drift

- Verify README setup/run commands resolve (e.g., every `npm run X` referenced exists in `package.json`).
- Sample-check 5–10 external links via HEAD/GET. **Network is permitted; this check is MANDATORY unless network is genuinely unavailable.** Skipping on plausibility heuristics ("the links look live") is not acceptable. Acceptable skip reasons: unreachable network, all 10 requests timed out. If the canonical docs genuinely contain zero external links — or fewer than 10, in which case sample what exists — state the result affirmatively in the report (e.g., "No external links in canonical docs — vacuously satisfied" or "N external links checked, all reachable"). Zero-link or low-link is a valid finding result, not a skip; it should not appear in either Hard Skips or Discretionary Skips.
- Flag stale `TODO`/`FIXME`/`HACK`/`XXX` markers strictly older than 6 months (via `git blame`). Exception: if the marker contains explicit deadline language ("by Q1 2026", "before v2.0") that has passed, flag it regardless of age.
- Flag badge mismatches (license badge vs `LICENSE`, version badge vs manifest).

### 5. Repository Hygiene

- `.gitignore` coverage per detected stack.
- Accidentally committed: build outputs (`dist/`, `build/`, `target/`, `*.pyc`, `__pycache__/`, `node_modules/`), IDE-local config (`.vscode/settings.json` with personal paths, `.idea/`), OS junk (`.DS_Store`, `Thumbs.db`, `desktop.ini`), large binaries (>1 MB unless intentional).
- Broken signals: scripts pointing at missing files; CI configs referencing removed actions; lockfile-manifest divergence.

### 6. Configuration Risk

- Debug/dev flags enabled in production-looking configs.
- Hardcoded localhost/staging/test endpoints in production code paths.
- Permissive CORS (`*`), disabled TLS verification, default credentials in non-template configs.
- Insecure framework defaults.

### 7. License & Legal

- `LICENSE` (or equivalent) present at repo root, matching what the README/manifest declares.
- Dependency licenses incompatible with the project's declared license.
- Missing attribution files where required by bundled licenses.

### 8. Open Observations (Speculative Pass)

A deliberately curious pass: surface anything that looks off, surprising, or worth a second look — even if it doesn't fit one of the categories above. Architectural smells, naming inconsistencies, dead/orphaned code, test gaps in critical modules, build/CI oddities, drift from Raiden documentation, anything that pattern-matches as "huh, that's strange."

Findings default to Low or Info unless they cross another category's threshold. Prefix uncertain observations with `(speculative)`.

## Severity Scheme

- **Critical** — any secret/credential/API key in working tree or git history (zero tolerance); exploitable RCE/SQLi/auth-bypass pattern; EOL runtime with known active CVEs.
- **High** — known CVE in a production dependency, hardcoded credential of any kind, missing/disabled security controls in shipping code.
- **Medium** — significantly outdated major versions, deprecated APIs in active use, doc drift severe enough to break setup.
- **Low** — minor hygiene, stale TODOs, cosmetic doc inconsistencies.
- **Info** — observations, suggestions, positive signals.

## Remediation Routing

Every actionable finding (one with a Recommended action) is tagged with routing metadata. Info-level findings with no recommended action are exempt.

### Step 1: Apply scoped routing config if found

If a scoped routing config exists (`.raiden/local/ROUTING.md`, `.raiden/routing.md`, `.raiden/models.md`, `.raiden/agents.md`, a routing section in `RAIDEN.md`, or — for framework repos and non-Instance targets — root-level equivalents like `routing.md`, `models.md`, or routing sections in canonical governance docs), its assignments are authoritative for the Recommended model field. Use them verbatim where they cover the finding type.

### Step 2: For findings not covered by scoped config, classify by class

| Class | Description | Default ladder rung |
|---|---|---|
| MECHANICAL | Deterministic edit, no judgment (version bump, `.gitignore` line, license field) | Any rung cleared for mechanical work |
| TARGETED-FIX | Bounded change, 1–2 files (broken link, single-function bug, stale TODO triage) | The lowest rung trusted with a bounded fix unsupervised |
| MULTI-FILE-REFACTOR | Coordinated changes across many files (rename, API migration, structural reorg) | A judgment-appropriate rung for coordinated multi-file work |
| SECURITY-CRITICAL | Careful review required (CVE remediation, credential rotation, auth/crypto, history rewrite) | The top available rung |
| CONFIG/CI | Workflows, build config, scripts; validation-oriented | The lowest rung trusted with validation-oriented config work |
| DOC-EDIT | README, markdown, comments only | Any rung cleared for mechanical work |
| SPECULATIVE-TRIAGE | First decide whether to act; two-stage (triage → class-appropriate remediation if confirmed real) | The top available rung |

Rungs are defined by `ROUTING_POLICY.md` and resolved to concrete models through the operator's local mapping (`.raiden/local/ROUTING.md`). When in doubt between two classes, the more cautious class wins — prefer the higher rung; when in doubt, one rung up.

### Step 3: Write a remediation seed

For each actionable finding, write a 1–2 sentence remediation seed describing what a downstream remediation prompt would need to accomplish. Seeds are structured as bounded-task handoffs to a downstream agent — the seed contains scope, target file(s), success criterion, and any necessary context. See `toolkit/prompts/handoff-template.md` for the canonical handoff shape.

## Process

1. Detect ecosystems and which read-only tools are available in the runtime environment.
2. Read the target's canonical orientation. For RAIDEN Instances: `AGENTS.md` → `.raiden/README.md` → `.raiden/state/CURRENT_STATE.md` → `.raiden/state/OPEN_LOOPS.md`. For framework repos or other non-Instance targets without a `.raiden/` layer: read the root-level canonical docs that exist (typically `README.md`, governance docs like `GOVERNANCE.md` or `REPOSITORY_MAP.md`, and any present state files like `CURRENT_STATE.md`, `OPEN_LOOPS.md`, `DECISIONS.md`).
3. Locate scoped model-routing config if present.
4. Plan per-category checks; skip cleanly when a tool is missing or an ecosystem is absent.
5. Execute read-only commands. Capture relevant output.
6. Consolidate findings, deduplicate, assign severity.
7. Tag each actionable finding with Remediation class, Recommended model, and Remediation seed.
8. Write the audit report (path below).
9. Publish state summary (paths below).

## Output

### Audit Report — Filename

Write a single Markdown file at:

```
audit-reports/audit-YYYY-MM-DD-<short-sha>.md
```

Where:
- `YYYY-MM-DD` is the current local date when the audit runs
- `<short-sha>` is the first 7 characters of the HEAD commit SHA being audited

**Collision handling:** if a file with this exact name already exists (re-running the audit on the same commit on the same day), append `-HHMMSS` (current local time, 24-hour, zero-padded) before the `.md` extension to avoid overwriting. Example:

- First run today on commit `abc1234def...`: `audit-2026-05-13-abc1234.md`
- Same-day rerun of same commit at 17:42:30 local: `audit-2026-05-13-abc1234-174230.md`

Create the `audit-reports/` directory if absent.

### Audit Report — Required Sections

- **Executive Summary** — repository, commit, branch, severity counts, remediation-routing counts, top 3 priorities
- **Orientation Layer** — canonical-docs location and status, routing config path or "Not found — class defaults applied", open loops referenced, layout notes
- **Findings** — per category, per-finding ID/severity/class/model/location/evidence/why/action/seed; "No findings." where applicable; Category 2 leads with the production/development split
- **Remediation Plan** — actionable findings grouped by class, ordered severity-then-ID within class, with model assignment per class
- **Appendix** — ecosystems detected, tools used, routing source, Hard Skips (tool/ecosystem unavailable), Discretionary Skips (with justification — mandatory checks must NOT appear here), optional Working-Tree Context, approximate duration

### State Publication

After the report is written, the audit agent publishes two state files. Both reference the exact filename of the report just written (including any `-HHMMSS` suffix used for collision avoidance).

`AUDIT_LOG.md` and `last-audit.md` are **protocol-owned state files**, canonized in state schema v2 (`toolkit/instance/STRUCTURE.md`). They are created and maintained by this protocol, not by hand, and are gitignored on public Instances per D-0038 (they carry operational vulnerability intelligence).

If `.raiden/state/` exists in the audited repo, publish to the canonical paths below. If `.raiden/state/` does not exist (target is a framework repo or non-Instance), fall back to publishing alongside the audit report at `audit-reports/AUDIT_LOG.md` and `audit-reports/last-audit.md`. The Appendix MUST note which path set was used.

**1. `.raiden/state/AUDIT_LOG.md` (rolling, append-only)** — prepend a new entry to the top of the entries section:

```
## YYYY-MM-DD (commit <short-sha>, branch <name>)

- Findings: Critical N | High N | Medium N | Low N | Info N
- Routing: Mechanical N | Targeted-fix N | Multi-file N | Security-critical N | Config/CI N | Doc-edit N | Speculative-triage N
- Report: audit-reports/audit-YYYY-MM-DD-<short-sha>[-HHMMSS].md
- Top priority: <one-line summary of #1 priority>
```

If `AUDIT_LOG.md` doesn't exist, create it with a brief header and the first entry.

**2. `.raiden/state/last-audit.md` (latest-only, overwritten)** — replace the file contents with:

```
# Last Workspace Audit

- Date: YYYY-MM-DD
- Commit: <short-sha>
- Branch: <name>
- Report: audit-reports/audit-YYYY-MM-DD-<short-sha>[-HHMMSS].md
- Findings: Critical N | High N | Medium N | Low N | Info N
- Top 3 priorities:
  1. <one-line>
  2. <one-line>
  3. <one-line>
```

The audit agent does NOT modify `CURRENT_STATE.md`, `OPEN_LOOPS.md`, `DECISIONS.md`, or `WORK_LOG.md`. Operator curation owns those. Critical and High findings warrant operator-side `OPEN_LOOPS.md` entries, but the audit recommends rather than writes them — the report's Remediation Plan section is the operator's queue.

## Reporting Discipline

- Redact secret values (`AKIA****`). Record location and type, never the secret itself.
- Every finding cites a path and, where possible, a line number.
- Zero findings in a category is a valid result. Write "No findings." and move on. Do not pad.
- Confidence labels: prefix uncertain findings with `(low-confidence)` or `(speculative)`.
- No remediation execution. Recommendations only.
- Routing fields only on actionable findings.
- Use class defaults verbatim when scoped routing doesn't cover a finding. Do not invent novel model assignments or editorialize on the maintainer's scoped choices.
