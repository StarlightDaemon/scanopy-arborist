<!-- mcp-name: io.github.OWNER/scanopy-arborist-mcp -->
# Arborist

**An MCP server for [Scanopy](https://scanopy.net)** — query your self-hosted network topology from Claude (or any MCP client) and curate the human-owned overlay without ever touching what the scanner discovered.

> **`OWNER` is a placeholder.** Replace it with your GitHub username/org (lowercase —
> container registries reject uppercase image names) before building or publishing. It
> appears in `pyproject.toml`, `deploy/docker/docker-compose.yml`,
> `deploy/podman/arborist.container`, the `deploy/lxc/` scripts, and this README.

The name plays on *scan* + *canopy*: an arborist tends the canopy view — pruning names, shaping tags, deciding what is visible — without touching the tree's structural integrity.

> Arborist integrates with Scanopy — https://scanopy.net

## The scope boundary

Arborist enforces a hard write boundary. Scanopy's scanner owns everything it discovered; Arborist only ever writes the curated overlay:

| Layer | Contents | Arborist may write? |
|---|---|---|
| **Discovered** | hostnames, IPs, MACs, ports, detected services, interfaces, subnets, VLANs | **Never** — read-only by construction |
| **Curated overlay** | host display name / description / hidden flag, tags, service bindings, opt-in host consolidation | Yes, under `ARBORIST_PROFILE=readwrite` |

Host updates go through a read-modify-write path that echoes discovered fields back verbatim and never sends child arrays, so a write cannot clobber scanner data even accidentally. Every tool response is also passed through a credential redactor before it reaches the model.

### Network-scope confinement

When `SCANOPY_NETWORK_ID` is set, Arborist refuses to *modify* anything outside that network. For network-scoped entities (hosts, services, subnets, bindings, …) it verifies the resolved entity's `network_id` before every write — including when you address it by a raw UUID, which Scanopy does not network-filter server-side.

Some Scanopy resources are **organization-scoped, not network-scoped** — a tag, for example, has no `network_id` of its own. For those, confinement is decided by the operation's *reach*, tiered by severity (full analysis: `docs/scope-confinement-audit.md`):

- **Create** (`create_tag`) touches no existing entity and proceeds.
- **Mutate** (`update_tag`) changes the shared label everywhere the tag is referenced, so a scoped session scans every *visible* use and refuses if any falls outside — or cannot be attributed to — the configured network.
- **Destroy** (`delete_tag`) is **always refused under a network scope.** Scanopy also accepts tags on user API keys, which an API key cannot read back (verified live: 403 on `/api/v1/auth/keys`), so no scan can prove an org-wide deletion stays in scope. Delete tags from an unscoped Arborist (the two-phase `confirm` flow still applies) or the Scanopy UI. A live canary test re-derives Scanopy's taggable-entity set on every integration run and fails loudly if it drifts from what these checks assume.

## Supported Scanopy versions

Verified live against **Scanopy 0.17.3**; supported range **`>=0.17.2,<0.18.0`**.

Scanopy is pre-1.0 and documents that breaking API changes may land in *any* release. Arborist therefore treats an unrecognized server version as a **refusal, not a warning**: at startup it checks `server_version`/`api_version` and exits (code 3) if the target is outside the verified range. To proceed anyway — at your own risk — set `ARBORIST_ALLOW_UNTESTED_VERSION=true`; Arborist will start and log a loud warning.

## The two credentials

Arborist uses up to two secrets. They are deliberately unrelated — do not reuse one as the other:

1. **`SCANOPY_API_KEY`** — a Scanopy **user API key** (starts with `scp_u_`), created in Scanopy under **Platform > API Keys**. This is Arborist's *outbound* credential. Recommendations:
   - **Viewer**-permission key for the `readonly` profile; **Member** or **Admin** for `readwrite` (creating tags requires **Admin**).
   - API keys are scoped to a list of network ids. **Pitfall:** an *empty* network list means access to **no** networks, not all of them — explicitly select the networks the key should see.
2. **`ARBORIST_AUTH_TOKEN`** — Arborist's *own* HTTP gate secret (any random string, ≥ 16 chars). Inbound MCP clients must present it as `Authorization: Bearer <token>`. Required for the HTTP transport only; it is never sent to Scanopy.

The default **stdio** transport needs only credential (1).

## Quickstart

Install the `arborist` command (Python ≥ 3.11). v0.1.0 is distributed from the git
repository, not PyPI:

```sh
uv tool install git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0
# or: pip install git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0
```

### Claude Code (stdio)

```sh
claude mcp add arborist \
  -e SCANOPY_BASE_URL=http://scanopy.lan:60072 \
  -e SCANOPY_API_KEY=scp_u_xxxxxxxx \
  -- arborist
```

Add `-e ARBORIST_PROFILE=readwrite` to enable the curation tools.

### Claude Desktop (stdio)

`claude_desktop_config.json` — no install needed if you have `uv` (uvx fetches the package on demand):

```json
{
  "mcpServers": {
    "arborist": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0", "arborist"],
      "env": {
        "SCANOPY_BASE_URL": "http://scanopy.lan:60072",
        "SCANOPY_API_KEY": "scp_u_xxxxxxxx"
      }
    }
  }
}
```

(If you installed the package, use `"command": "arborist"` with no args instead.)

### HTTP mode (Streamable HTTP)

```sh
export SCANOPY_BASE_URL=http://scanopy.lan:60072
export SCANOPY_API_KEY=scp_u_xxxxxxxx
export ARBORIST_AUTH_TOKEN="$(openssl rand -hex 24)"

arborist --transport http        # serves http://127.0.0.1:60074/mcp
```

```sh
claude mcp add --transport http arborist http://127.0.0.1:60074/mcp \
  --header "Authorization: Bearer $ARBORIST_AUTH_TOKEN"
```

Unauthenticated requests get a 401. Binding beyond loopback requires a declared TLS posture — see below.

## Configuration reference

All configuration is via environment variables. `SCANOPY_*` describes the target Scanopy instance; `ARBORIST_*` describes Arborist's own behavior.

| Variable | Default | Used by | Description |
|---|---|---|---|
| `SCANOPY_BASE_URL` | *(required)* | both | Scanopy URL, e.g. `http://scanopy.lan:60072`. Must start with `http://` or `https://`. |
| `SCANOPY_API_KEY` | *(required)* | both | Scanopy user API key (`scp_u_...`), Platform > API Keys. |
| `SCANOPY_NETWORK_ID` | unset | both | Pin Arborist to one Scanopy network: list tools default to it, and writes to entities outside it are refused. Org-scoped resources are tiered — tag creation proceeds, tag updates fail closed on visible out-of-scope use, tag deletion is always refused (see "Network-scope confinement"). |
| `SCANOPY_TLS_VERIFY` | `true` | both | Verify Scanopy's TLS certificate. |
| `SCANOPY_TLS_CA_PATH` | unset | both | Custom CA bundle for verifying Scanopy. Mutually exclusive with `SCANOPY_TLS_VERIFY=false`. |
| `ARBORIST_PROFILE` | `readonly` | both | `readonly` or `readwrite`. Gates which tools are registered at all. |
| `ARBORIST_ENABLE_CONSOLIDATION` | `false` | both | Register `consolidate_hosts`. Requires `ARBORIST_PROFILE=readwrite`. |
| `ARBORIST_ALLOW_UNTESTED_VERSION` | `false` | both | Escape hatch for the startup version guard (loudly logged). |
| `ARBORIST_TRANSPORT` | `stdio` | CLI | `stdio` or `http`. CLI flag `--transport` overrides. |
| `ARBORIST_BIND_HOST` | `127.0.0.1` | http | HTTP bind host. CLI flag `--host` overrides. |
| `ARBORIST_BIND_PORT` | `60074` | http | HTTP bind port. CLI flag `--port` overrides. |
| `ARBORIST_AUTH_TOKEN` | unset | http | Arborist's bearer gate secret, ≥ 16 chars. Required for HTTP. |
| `ARBORIST_ALLOWED_HOSTS` | unset | http | Comma-separated `Host` header allowlist (DNS-rebinding protection). Required for non-loopback binds. |
| `ARBORIST_TLS_POSTURE` | `loopback` | http | `loopback`, `terminated-upstream`, or `direct` — see below. |
| `ARBORIST_TLS_CERT_PATH` | unset | http | TLS certificate, required when posture is `direct`. |
| `ARBORIST_TLS_KEY_PATH` | unset | http | TLS private key, required when posture is `direct`. |

### TLS posture (HTTP transport hardening)

`ARBORIST_TLS_POSTURE` is a declaration of who provides transport security:

- **`loopback`** (default) — Arborist refuses to bind any non-loopback address.
- **`terminated-upstream`** — plain HTTP on non-loopback binds is acceptable because TLS/isolation is handled outside Arborist (reverse proxy, container network, tunnel).
- **`direct`** — Arborist serves TLS itself; both `ARBORIST_TLS_CERT_PATH` and `ARBORIST_TLS_KEY_PATH` are required.

The HTTP transport **refuses to start** (exit code 4) when any of these hold:

- `ARBORIST_AUTH_TOKEN` is missing or shorter than 16 characters;
- the bind host is non-loopback while posture is `loopback`;
- the bind host is non-loopback and `ARBORIST_ALLOWED_HOSTS` is empty;
- posture is `direct` without both cert and key paths.

### Exit codes

| Code | Meaning |
|---|---|
| `2` | Configuration error (missing/invalid env vars). |
| `3` | Version guard refused the target Scanopy (outside `>=0.17.2,<0.18.0`). |
| `4` | HTTP transport security refused (see conditions above). |
| `5` | Scanopy unreachable (DNS, connection refused, TLS handshake, ...). |

## Profiles and tools

Profile gating is structural: tools outside the active profile are **never registered**, so a readonly Arborist has no write tools for a client to even attempt. Destructive and bulk operations are **two-phase**: called without `confirm=true` they return a plan/preview and change nothing.

### `readonly` (default) — 14 read tools

| Tool | Description |
|---|---|
| `get_instance_info` | Scanopy version, Arborist profile, consolidation flag, network scoping — call first to orient. |
| `list_networks` | Networks visible to this API key. |
| `list_hosts` | Compact host summaries; filter by tag, substring search, pagination. |
| `get_host` | Full detail for one host — by id, name, hostname, IP, or MAC. |
| `list_services` | Detected services (name, catalog definition, owning host). |
| `list_subnets` | Subnets (CIDR, name, type), incl. Scanopy's synthetic Internet/Remote subnets. |
| `list_ports` | Discovered open ports across hosts. |
| `list_host_addresses` | IP address records: IP, MAC, owning host, subnet. |
| `list_snmp_interfaces` | SNMP ifTable entries with LLDP/CDP neighbor info. |
| `list_dependencies` | Service dependency edges. |
| `list_tags` | All tags (id, name, color, `is_application`). |
| `list_bindings` | Service bindings (how services attach to ports/IPs). |
| `get_topology` | Topology record and view options for a network. |
| `export_topology_mermaid` | Export topology as a Mermaid flowchart (`L2Physical`, `L3Logical`, `Workloads`, `Application`). |

### `readwrite` — adds 11 curated-overlay write tools

| Tool | Description |
|---|---|
| `update_host_metadata` | Set display name, description, and/or hidden flag on one host. |
| `set_host_tags` | Replace the full tag set on a host. |
| `bulk_update_hosts` | Metadata updates across many hosts — two-phase (plan, then `confirm=true`). |
| `create_tag` | Create a tag (color, `is_application`). Requires an Admin-level key. |
| `update_tag` | Rename or restyle an existing tag. |
| `delete_tag` | Delete a tag — the label disappears org-wide. Requires `confirm=true`; always refused when `SCANOPY_NETWORK_ID` is set (see "Network-scope confinement"). |
| `tag_entities` | Add one tag to many hosts/services/subnets/networks/dependencies. |
| `untag_entities` | Remove one tag from many entities. |
| `create_binding` | Bind a service to a port or IP on its host. |
| `update_binding` | Modify an existing binding. |
| `delete_binding` | Delete a binding. Requires `confirm=true`. |

### `ARBORIST_ENABLE_CONSOLIDATION=true` — adds 1 tool

| Tool | Description |
|---|---|
| `consolidate_hosts` | Merge duplicate host records: source's interfaces/ports/services move to destination, source is deleted. Two-phase with a merge preview. |

Consolidation never edits discovered values — it reassigns which host record owns them — but its blast radius is bigger than a rename, hence the separate opt-in flag.

## Deployment

### Docker Compose — `deploy/docker/`

`deploy/docker/Dockerfile` (multi-stage uv build, non-root runtime) and `deploy/docker/docker-compose.yml`:

```sh
cd deploy/docker
cp .env.example .env      # fill in SCANOPY_BASE_URL, SCANOPY_API_KEY, ARBORIST_AUTH_TOKEN
docker compose up -d
```

The compose file publishes port 60074 to the Docker host's **loopback only**. Inside the container Arborist binds `0.0.0.0` with `ARBORIST_TLS_POSTURE=terminated-upstream` — if you widen the publish, put a TLS-terminating reverse proxy in front and extend `ARBORIST_ALLOWED_HOSTS`.

### Podman Quadlet — `deploy/podman/arborist.container`

Requires podman ≥ 4.6. Create the two secrets first (as the user that runs the container):

```sh
printf %s "<scanopy-api-key>"          | podman secret create scanopy-api-key -
printf %s "$(openssl rand -hex 32)"    | podman secret create arborist-gate-token -
```

Then install the unit — rootful: copy to `/etc/containers/systemd/`, `systemctl daemon-reload && systemctl start arborist`; rootless: copy to `~/.config/containers/systemd/`, `systemctl --user daemon-reload && systemctl --user start arborist`, and for start-at-boot without a login session:

```sh
loginctl enable-linger <user>
```

Secrets are injected as env vars at runtime and never appear in the unit file or `podman inspect`. See `deploy/podman/README.md` for auto-update and verification steps.

### Proxmox LXC — `deploy/lxc/`

`deploy/lxc/ct/arborist.sh` (container-creation script) and `deploy/lxc/install/arborist-install.sh` (in-container installer), written in the [community-scripts](https://github.com/community-scripts) format. Run `ct/arborist.sh` on a Proxmox VE host to create a minimal LXC running Arborist as a systemd service. The pair is formatted for submission to **ProxmoxVED** (the community-scripts development repo where new scripts land first); until merged upstream, run it from this repo.

## Limitations (beta)

- **No SVG export.** Scanopy renders SVG client-side only; `export_topology_mermaid` is the machine-readable path.
- **No Groups tools.** Scanopy 0.17.x has no Groups REST resource; tags — including `is_application` tags, which group services into applications — are the grouping mechanism.
- **Pre-1.0 upstream API.** Hence the strict version guard; expect Arborist releases to track Scanopy releases.

## Development

```sh
git clone https://github.com/OWNER/scanopy-arborist-mcp
cd scanopy-arborist-mcp
uv sync
uv run pytest tests/unit             # unit tests — no network needed
```

### Integration tests

The integration suite (`uv run pytest tests/integration`, marker `integration`) runs against a **live, disposable** Scanopy instance — it creates, mutates, consolidates, and deletes records. Safety rail: the whole suite skips unless the `SCANOPY_BASE_URL` host is loopback, or you explicitly set `ARBORIST_TEST_ALLOW_REMOTE=1`. Credentials come from `SCANOPY_BASE_URL`/`SCANOPY_API_KEY`/`SCANOPY_NETWORK_ID`, or from a `KEY=value` file pointed to by `ARBORIST_TEST_ENV_FILE` (kept outside the repo so the key is never committed).

### Standing up a disposable Scanopy

1. Run Scanopy via Docker Compose using the compose file from the [scanopy/scanopy](https://github.com/scanopy/scanopy) repo (images `ghcr.io/scanopy/scanopy/server` and `.../daemon`; the server listens on port 60072).
2. Headless first-run bootstrap (or just use the web UI): with a cookie jar, `POST /api/auth/setup`, then `POST /api/auth/register` **in the same session**.
3. Create a user API key (Platform > API Keys in the UI) and export it as `SCANOPY_API_KEY`.

## License

Arborist is **MIT-licensed** (see `LICENSE`). Scanopy itself is **AGPL-3.0**; Arborist is a separate client that speaks only to Scanopy's documented HTTP API and contains no Scanopy code.

Arborist integrates with Scanopy — https://scanopy.net
