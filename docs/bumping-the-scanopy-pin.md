# Runbook: bumping the Scanopy compatibility pin

Arborist hard-refuses Scanopy versions outside the range in
[`src/arborist/compat.py`](../src/arborist/compat.py) (`MIN_SUPPORTED` /
`MAX_EXCLUSIVE`), because Scanopy documents that breaking API changes may land
in **any** pre-1.0 release. Widening the range is a verification exercise, not
an edit. Do not bump the pin without walking this list against a live instance
of the new version.

## 1. Stand up a disposable instance of the target version

```sh
mkdir scanopy-pin-test && cd scanopy-pin-test
curl -sSLo docker-compose.yml https://raw.githubusercontent.com/scanopy/scanopy/main/docker-compose.yml
# Pin the server/daemon image tags to the target release, then:
docker compose up -d
```

Bootstrap headlessly (same session cookie across both calls):
`POST /api/auth/setup` `{"organization_name": ..., "network": {"name": ...}}` →
`POST /api/auth/register` `{"email", "password", "terms_accepted": true}` →
create a user API key via `POST /api/v1/auth/keys` (include `network_ids`;
an empty list means access to NO networks).

## 2. Re-run the Stage-0-style checks

Each maps to an assumption baked into the client — check them **on the new
version**, not from memory:

1. `GET /api/version` — envelope shape `{success, data:{api_version,
   server_version}, meta}` unchanged; `api_version` still `1` (a bump is an
   automatic stop — the client targets api_version 1).
2. `GET /api/v1/hosts/{id}` — `name`, `description`, `hidden`, `hostname`
   fields present; children arrays (`ip_addresses`, `ports`, `services`,
   `interfaces`) still embedded.
3. `PUT /api/v1/hosts/{id}` — still full-replace with `UpdateHostRequest`
   semantics: omitted `tags` **clears** them; omitted child arrays preserve.
   Verify with a rename round-trip on a discovered host and confirm children
   and tags are untouched. Check `expected_updated_at` still works.
4. OpenAPI spec — compare `ui/static/openapi.json` in the release tag against
   the previous one; diff the paths/schemas Arborist touches (hosts, tags,
   bindings, topology, auth/keys, consolidate).
5. API key auth — `Authorization: Bearer scp_u_...` still accepted;
   Viewer/Member/Admin permission behavior unchanged; API access still
   included in the Community plan (watch for 402s).
6. `GET /api/v1/tags` + tag assign endpoints (`PUT /api/v1/tags/assign`,
   `POST /api/v1/tags/assign/bulk-add|bulk-remove`) unchanged. Check whether a
   Groups resource has appeared (`/api/v1/groups` returning JSON, not the SPA
   HTML fallback) — if so, consider the deferred Groups tools.
7. Consolidation — `PUT /api/v1/hosts/{dest}/consolidate/{other}` unchanged,
   including its validation errors (same-host, cross-network, daemon-attached).
8. Rate limiting — 429 + `Retry-After` + `X-RateLimit-*` headers still present.
9. Mermaid export — `GET /api/v1/topology/{id}/export/mermaid` still exists
   (it is tagged `internal` upstream, so it can move without notice).

## 3. Run the integration suite against the new version

Temporarily widen `MAX_EXCLUSIVE` locally, then:

```sh
SCANOPY_BASE_URL=http://localhost:60072 SCANOPY_API_KEY=scp_u_... \
  uv run pytest tests/integration -q
```

All tests must pass unmodified. Test failures are findings about the new
version, not about the tests.

## 4. Land the bump

- Update `MIN_SUPPORTED`/`MAX_EXCLUSIVE` in `src/arborist/compat.py` and the
  range strings in `README.md` and `tests/` where asserted.
- Record the verified version and date in `CHANGELOG.md`.
- If anything in step 2 changed shape, that is a code change + tests first,
  pin bump second.
