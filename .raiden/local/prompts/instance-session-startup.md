# Instance Session Startup Template

## Prompt ID

`raiden.instance.session-startup.v1`

## Purpose

Use this prompt at the start of any RAIDEN Instance agent session to review
repo state, surface unpushed work, and obtain a scoped token from the operator
before pushing.

Designed to be reusable across all RAIDEN Instance repos without modification.
The operator fills in the repo name at launch.

## Target Agent

Any RAIDEN Instance embedded agent. Model-agnostic. No elevated reasoning level
required — this is a state-check and operator-confirmation flow, not deep
planning work.

## Template

```text
You are starting a session in a RAIDEN Instance repo.

Read first:
- AGENTS.md
- .raiden/README.md
- .raiden/state/CURRENT_STATE.md (if present)

Then run:
- git status
- git log --oneline -10
- git remote -v

Report to the operator:
- current branch
- number of unpushed commits (if any), with their one-line summaries
- any uncommitted changes
- any untracked files that look like work product (not node_modules, build
  output, or generated files)

Then ask the operator: "Do you want to push the unpushed work?"

If yes, request a token:

  "Please generate a fine-grained GitHub PAT for this repo with:
   - Repository access: this repo only (<repo name>)
   - Contents: Read and write
   - Pull requests: Read and write
   - Metadata: Read (required, auto-set)
   - Expiry: 1 day
   Paste the token here when ready."

Once the token is provided:
- Authenticate: echo "<token>" | gh auth login --with-token
- Verify: gh auth status
- Push: git push origin <branch>
- Confirm success to the operator

Do not:
- push without operator confirmation
- request broader token scope than listed above
- store or log the token beyond what is needed to authenticate and push
- commit or stage any files without explicit operator instruction
```

## Notes

- Fits the planned "operator-facing kickoff prompts" category from
  `GOVERNANCE.md`.
- Token scope rule (fine-grained, repo-scoped, 1-day expiry) matches the
  operator's session-token rotation policy.
- The operator voids or allows the token to expire after each session by
  design — do not suggest reuse across sessions.
