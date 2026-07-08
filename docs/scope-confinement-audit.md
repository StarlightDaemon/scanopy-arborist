# Scope-confinement audit — every write tool vs. Scanopy's full resource list

**Date:** 2026-07-07 · **Scanopy:** 0.17.3 (live disposable instance) ·
**Arborist:** working tree at this commit
**Method:** empirical probe against the live API as primary evidence, Scanopy
source (0.17.3 clone) as corroboration, canary tests to catch drift.

## Why this audit exists

Two consecutive fixes to `delete_tag`'s scope confinement were incomplete for
the same reason: a hand-enumerated list of "entity types a tag can reach" that
was narrower than what the server actually accepts (first 5 types, then a
review-reported "10 types" figure that itself had never been verified live).
The general lesson, applied here to **every** write tool: *an operation's
reach must be derived from what Scanopy does — probed empirically and pinned
by a canary — not from what its docs, its reviewers, or its own tool authors
believe it does.*

## 1. Ground truth: what can a tag actually reach?

### 1.1 Empirical probe (primary evidence)

Probe scripts (session scratchpad `probe_taggable.py`, `probe_final3.py`,
`probe_dep.py`) ran against live Scanopy 0.17.3:

1. `PUT /api/v1/tags/assign` was called with **27 candidate entity_type
   spellings** covering all 21 resource families in the handoff's resource
   list plus plausible aliases. serde's *unknown variant* rejection
   distinguishes "not in the enum" from runtime rejections, and the server
   answers `"Entity type X does not support tagging"` for enum members that
   refuse tags, so three classes emerge from live behavior alone:

   | Class | Types |
   |---|---|
   | **Taggable (10)** — assignment succeeds | Host, Service, Subnet, Network, Dependency, Credential, Daemon, DaemonApiKey, UserApiKey, Discovery |
   | In enum, refuses tagging (11) | Binding, Interface, Invite, Organization, Port, Share, Snapshot, Tag, Topology, User, Vlan |
   | Not in the enum | Group, IfEntry, IpAddress, ApiKey, DiscoveryJob, DiscoverySchedule, … |

2. **Every one of the 10 was verified with a real instance** — including
   Credential, UserApiKey, and Dependency, for which instances were created
   during the probe (the "10 types" figure from the previous review was
   treated as a hypothesis, not a fact, until each type had a live
   assignment + read-back). Tag visible in read-back for all 9 readable
   types; UserApiKey verified via session auth (see 1.3).

3. **Network attribution per taggable type** (from live records):

   | Type | Attribution | Scope class |
   |---|---|---|
   | Host, Service, Subnet, Dependency, Daemon, DaemonApiKey, Discovery | `network_id` scalar | network-scoped |
   | Network | its own `id` | network-scoped (self) |
   | Credential | `assigned_network_ids` **list** (may be empty) + `organization_id` | org-scoped |
   | UserApiKey | `network_ids` **list** (may be empty) + `organization_id` | org-scoped |

4. **The UserApiKey blind spot.** Under API-key auth, `GET /api/v1/auth/keys`
   and `GET /api/v1/auth/keys/{id}` both answer **403
   "User context required"** — yet `PUT /api/v1/tags/assign` for a UserApiKey
   **succeeds** with the same key. Tags on user API keys therefore exist,
   can even be created by Arborist's credentials, but can never be
   enumerated or read back by them. **No usage scan performed with an API
   key can ever be complete.**

5. **Tag deletion is a soft-close, not a cascade.** After
   `DELETE /api/v1/tags/{id}` (HTTP 200), the tag vanishes from
   `/api/v1/tags`, but every previously tagged entity still carries the tag
   UUID in its `tags` array (verified across 9 types). Corroborated by
   source: the delete handler soft-closes the SCD2 row (`valid_to = NOW()`),
   so the `entity_tags` junction's `ON DELETE CASCADE` never fires. The
   practical blast radius of deletion is *the org-wide destruction of the
   label* (plus dangling references), not a rewrite of out-of-scope rows —
   the fail-closed rationale is unchanged, but tool docstrings no longer
   claim "removed from every entity".

### 1.2 Source corroboration (secondary)

`EntityDiscriminants::is_taggable()`
(`backend/src/server/shared/entities.rs:217`) is an exhaustive match listing
exactly the 10 probed types. All tag application paths go through the
`entity_tags` junction table; no variant rejects at dispatch. Router
registration confirms the list paths used by `tag_usage()`. Where source
reading and the probe disagreed — the source suggested `/api/v1/auth/keys`
works under API-key auth; live it does not — **the probe wins**, which is
exactly why probing is the primary method.

### 1.3 Fix applied (SC8, third and final iteration)

- `ScanopyClient._TAG_USAGE_SOURCES` — rebuilt from the probe: all **9
  enumerable** taggable types with their attribution shape
  (`network_id` / self / `network_ids:<field>`).
- `ScanopyClient.TAG_USAGE_BLIND_TYPES = ("UserApiKey",)` — the probed blind
  spot, load-bearing for policy (below).
- `tag_usage()` returns list-shaped attribution
  (`network_ids: [...]`, `org_scoped: bool`); `usage_outside_scope()`
  classifies fail-closed: any record whose network set ≠ {scope}, **or with
  no attribution at all**, counts as outside.
- **Canary** (`tests/integration/test_tag_scope_canary.py`) re-derives the
  entire entity enum from the server's own serde error message, probes every
  variant for taggability, and asserts the derived sets equal the hardcoded
  constants; verifies each enumerable path still lists under API-key auth
  with the expected attribution field and `tags` exposure; asserts the blind
  types are **still blind** (if Scanopy ever opens `/api/v1/auth/keys` to API
  keys, the canary fails so the hard refusal below can be revisited). This
  canary fails loudly on exactly the drift class that caused both prior
  escapes.

## 2. Policy for org-scoped objects (tags today; template for anything later)

Confinement is decided by **reach**, tiered by severity:

| Operation | Reach | Scoped behavior |
|---|---|---|
| create (`create_tag`) | touches no existing entity | allowed |
| mutate (`update_tag`) | changes the shared label everywhere it is referenced; associations untouched (verified: rename does not cascade); reversible | allowed only when every **visible** use is in scope; refused on any out-of-scope or unattributable use |
| destroy (`delete_tag`) | destroys the label org-wide; blast radius includes uses that are **provably unknowable** under API-key auth | **always refused under scope** — no enumeration can prove safety, so there is no allow path to get wrong |

The delete rule is deliberately not "check what we can see": that design
failed twice. An org-wide destructive operation under a network-confinement
guarantee is refused outright; the operator deletes tags from an unscoped
Arborist (two-phase confirm still applies) or the Scanopy UI.

## 3. Coverage matrix — every write-capable tool

Reach derivation: **probe** = empirically probed live; **bounded** = the
operation can only ever touch its own resolved target(s), enforced by code
the audit read line-by-line; **canary** = pinned by the canary test.

| Tool | Direct reach | Cascading reach | Confinement mechanism | Derivation | Verdict |
|---|---|---|---|---|---|
| `update_host_metadata` | 1 Host | — | `assert_in_scope` immediately after resolve — **now also covers the no-op short-circuit** (F1) | bounded | **FIXED** (F1) |
| `set_host_tags` | 1 Host + tag associations on it | clear-path bulk-removes only from that host | `assert_in_scope(record)`; tag resolution is read-only | bounded | PASS |
| `bulk_update_hosts` | N Hosts | — | per-record `assert_in_scope` in plan AND apply; out-of-scope rows excluded from plan output | bounded | PASS |
| `create_tag` | new org-wide Tag object | none (no associations yet) | policy: creation allowed (§2) | probe+policy | PASS |
| `update_tag` | org-wide Tag object | label change visible on every entity referencing it (10 types incl. blind) | **NEW:** visible-usage scan via `tag_usage`; refuses on any out-of-scope/unattributable *visible* use (F3) | probe+canary | **PARTIAL — see F5.** More restrictive than before, but a tag whose only use is on a `UserApiKey` (invisible under API-key auth) still passes the guard. Handed back to the operator under Stop Condition 11. |
| `delete_tag` | org-wide Tag object | label destroyed for every referencing entity, incl. types invisible to API-key auth | **NEW:** unconditional refusal under scope (F2); unscoped: two-phase confirm + visible-usage plan | probe+canary | **FIXED** (F2) |
| `tag_entities` | ≤5 entity types (`_TAGGABLE`), N entities | — | client-side type gate (deliberately narrower than server's 10 — infrastructure types are out of charter); per-type scope checks in `_assert_entities_in_scope`; canary asserts `_TAGGABLE ⊆ _TAG_USAGE_SOURCES ⊆ server-taggable` | probe+canary | PASS |
| `untag_entities` | same as `tag_entities` | — | same gates | probe+canary | PASS |
| `create_binding` | 1 Binding (new, in service's network) | — | owning Service fetched + scope-checked; `network_id` derived from it, never caller-supplied | bounded | PASS (note N1) |
| `update_binding` | 1 Binding | — | existing binding `assert_in_scope` + service re-derivation as above | bounded | PASS (note N1) |
| `delete_binding` | 1 Binding | — | `assert_in_scope` + two-phase confirm | bounded | PASS |
| `consolidate_hosts` | 2 Hosts (dest mutated, source deleted) | source's interfaces/ports/services reassigned; bindings remapped — all within one network (server enforces same-network with 400) | both hosts `assert_in_scope` before even the preview; two-phase confirm; opt-in flag | bounded (+server rule verified in prior pass) | PASS |

**Reads:** `SCANOPY_NETWORK_ID` confines *writes*; read tools list through the
network filter by default but UUID reads are intentionally org-visible
(documented design, unchanged by this audit). The one write-tool leak of that
design — the no-op short-circuit — is F1, fixed.

### Notes

- **N1 (bindings, referential):** Scanopy's binding create/update validates
  *type conflicts* only within the binding's own network
  (`bindings/handlers.rs::validate_no_binding_type_conflict`); it does not
  verify that `port_id`/`ip_address_id` belong to the service's host or
  network. A caller could therefore reference an out-of-scope port UUID from
  an in-scope binding. The written row remains entirely inside the scoped
  network and the referenced record is **not modified**, so this is a
  data-quality wart (and an upstream validation gap), not a scope escape.
  Left unfixed deliberately; candidates for post-release hardening.
- **N2 (dangling tag references):** because deletion soft-closes (1.1 #5),
  long-lived instances accumulate orphaned tag UUIDs in `tags` arrays.
  `tag_usage()` matches by live tag id, so orphans are inert for
  confinement decisions.

## 4. Findings & fixes (this audit)

| # | Finding | Severity | Fix |
|---|---|---|---|
| F1 | `update_host_metadata` no-op short-circuit returned out-of-scope host metadata (scope assert only ran inside the PUT path) | low (info disclosure) | scope assert moved to immediately after resolve; unit + prior live tests cover both paths |
| F2 | `delete_tag`'s allow-path depended on an enumeration that is provably incompletable (UserApiKey blind spot) — the root cause of SC8 #1 and #2 | high | unconditional scoped refusal (§2); refusal message reports visible usage census + the blind-spot rationale |
| F3 | `update_tag` mutated the org-wide label with **no** usage check at all | medium | visible-usage fail-closed check (refuses on out-of-scope or unattributable use) |
| F4 | `tag_usage` scanned 5 of 9 enumerable taggable types; attribution model couldn't represent list-shaped (org-scoped) records | high (enabler of F2) | rebuilt from probe: 9 sources, list-shaped attribution, `usage_outside_scope` fail-closed classifier, canary |
| F5 | **`update_tag`'s visible-usage guard is incomplete — the same UserApiKey blind spot that forced `delete_tag` to refuse outright.** A scoped session can rename/restyle a tag whose only use is on an out-of-scope `UserApiKey`. | medium (reversible, label-only) — but same **bug class** as SC8 | **NOT FIXED — Stop Condition 11.** This is the third occurrence of an incomplete tag-scope fix; per the run's charter the design is handed back to the operator rather than auto-patched a fourth time (see §6 below). |

### F5 — Stop Condition 11 (tag-scope fix still incomplete, third occurrence)

The review gate's tag-escape lens found, and this session independently
reproduced live, that `update_tag` inherits the exact blind spot §2 uses to
justify `delete_tag`'s unconditional refusal. Reproduction
(`scratchpad/verify_updatetag_hole.py`): with `SCANOPY_NETWORK_ID` set, a tag
assigned **only** to a `UserApiKey` produces `tag_usage() == []` and
`usage_outside_scope([]) == []`, so the guard passes and the real `update_tag`
MCP tool committed a color change org-wide on that out-of-scope key.

Per the run charter (Stop Condition 11: *a third occurrence of an incomplete
tag-scope fix, found by this run's own review gate → halt; hand the design
back rather than attempt a fourth automatic fix*), **this is not auto-fixed.**
The committed state is still a strict improvement — before this pass
`update_tag` had **no** scope check at all — so it is safe to leave in place
while the operator decides the design. Candidate designs (operator's call):

1. **Extend `delete_tag`'s unconditional scoped refusal to `update_tag`**
   (smallest change, consistent with the policy already shipped; the
   recommendation if a same-class fix is authorized).
2. **Accept the residual** as documented, low-severity, reversible behavior
   (label-only, does not alter the key's permissions/networks).
3. **Session-auth escalation** — give Arborist user-session credentials so it
   can read `/api/v1/auth/keys` and obtain a complete usage census (larger
   change to the credential model).
4. **Narrow Arborist's tag surface** so tag mutations never consider
   org-scoped/blind types.

Root cause is structural to Scanopy 0.17.3: tags can be assigned to entities
an API key cannot read back, so **no** usage scan performed with an API key is
ever complete — any tag operation that reasons about "where is this tag used"
is working from an inherently partial picture. That is why the durable answer
for *destructive* org-wide ops was "refuse under scope," and why the same
question for *mutating* ops is a genuine design decision rather than a
mechanical patch.

**Stop-condition 10 was not triggered:** no critical scope gap was found in a
non-tag write tool. F1 was already known from the prior pass and carried
forward; the bindings referential note (N1) is a data-quality wart, not a
scope escape. F5 is squarely the tag-scope bug class (SC11), not SC10.

## 5. Test evidence

- `tests/unit/test_scope_audit.py` — source-set lockstep, attribution shapes,
  fail-closed classification matrix, always-refuse delete, update allow/refuse
  paths, no-op disclosure regression. (173 unit tests green.)
- `tests/integration/test_tag_scope_canary.py` — live drift canary (above).
- `tests/integration/test_fix_pass_live.py` — scoped delete refuses in ALL
  scope configurations incl. "everything visibly in scope"; unscoped
  delete works; scoped update refuses on out-of-scope *visible* use and
  proceeds when in scope. (29 integration tests green vs. live 0.17.3.)
- `scratchpad/verify_updatetag_hole.py` — the F5 reproduction (not committed;
  session-scratchpad evidence for the operator hand-back).

> **Note on test coverage vs. F5:** the current tests assert `update_tag`'s
> *visible-usage* fail-closed behavior, which passes. They do **not** yet
> cover the UserApiKey blind-usage case (that would require a test that the
> current code fails — appropriate to add alongside whichever design the
> operator picks, not before).
