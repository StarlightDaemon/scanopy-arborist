# Cutting a release (operator-run, manual)

Arborist releases are manual for now — no CI publishing, no PyPI. The v0.1.0
release is cut from `main` with the sequence below. Nothing in this file is
executed by tooling; run each step yourself after reviewing.

## Prerequisites

- `OWNER` replaced with the real GitHub org/user everywhere
  (`grep -rn OWNER --include='*.toml' --include='*.yml' --include='*.md' --include='*.container' --include='*.sh' .`
  should return nothing unexpected). Remember: lowercase for image references.
- A GitHub repository `github.com/<owner>/scanopy-arborist-mcp` with `main`
  pushed, and `gh` authenticated.
- The full test suite green against a disposable Scanopy instance:
  `uv run pytest tests/ -q` (see README "Development" for standing one up).

## Sequence

```sh
# 1. Final check of the working tree
git status                      # clean, on main
uv run pytest tests/unit -q     # fast sanity pass

# 2. Tag the release (annotated; version matches pyproject.toml)
git tag -a v0.1.0 -m "Arborist v0.1.0"

# 3. Push branch and tag
git push origin main
git push origin v0.1.0

# 4. Create the GitHub release with the changelog entry as notes
gh release create v0.1.0 \
  --title "Arborist v0.1.0" \
  --notes-file CHANGELOG.md \
  --verify-tag
```

The LXC update path (`check_for_gh_release` / `fetch_and_deploy_gh_release`)
starts working as soon as the first GitHub release exists.

## Container image (optional, for the compose/Quadlet `Image=` reference)

```sh
docker build -f deploy/docker/Dockerfile -t ghcr.io/<owner>/scanopy-arborist-mcp:v0.1.0 .
docker tag ghcr.io/<owner>/scanopy-arborist-mcp:v0.1.0 ghcr.io/<owner>/scanopy-arborist-mcp:latest
docker push ghcr.io/<owner>/scanopy-arborist-mcp:v0.1.0
docker push ghcr.io/<owner>/scanopy-arborist-mcp:latest
```

## Post-release

- Verify `pip install git+https://github.com/<owner>/scanopy-arborist-mcp.git@v0.1.0`
  installs and `arborist --version` prints `arborist 0.1.0`.
- PyPI publishing is deliberately out of scope for v0.1.0.
