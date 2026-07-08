# Using Arborist

This is a start-to-finish walkthrough for setting up Arborist and using it day to
day. For a quick reference (env var table, tool list), see the [README](../README.md) —
this document goes deeper into *why* and *how*, with real examples.

> **Current repo state, checked against this guide's own source:** as of this
> writing there is no `git remote`, no `v0.1.0` tag, and `OWNER` is still a
> literal placeholder throughout the repo (`pyproject.toml`,
> `deploy/docker/docker-compose.yml`, `deploy/podman/arborist.container`,
> `deploy/lxc/`). `arborist --version` prints `arborist 0.1.0b1` — the beta
> suffix from `pyproject.toml`, not the `v0.1.0` name used in the CHANGELOG and
> [RELEASE.md](../RELEASE.md). In other words: this is a **from-source install
> today**, not a cut release. Everything below is written to work against that
> reality; where the README or RELEASE.md shows a `git+https://github.com/OWNER/...`
> or `ghcr.io/OWNER/...` reference, that path only resolves once you (or
> whoever's running this repo) fills in `OWNER` and follows RELEASE.md to cut a
> tag and push it somewhere. This guide shows both: what works right now
> against your own checkout, and the form the same command takes once
> published.

## 1. What Arborist does

Arborist is an MCP server that lets Claude read your [Scanopy](https://scanopy.net)
network topology — hosts, services, ports, dependencies — directly in
conversation. Optionally, it also lets Claude curate the human-owned layer on
top of what Scanopy discovered (names, descriptions, tags, visibility) — but it
never writes to anything Scanopy's scanner actually found (hostnames, IPs,
ports, interfaces stay untouched, by construction, not just by policy).

## 2. Prerequisites

- A running, self-hosted Scanopy instance. Arborist is verified live against
  **Scanopy 0.17.3**, supported range `>=0.17.2,<0.18.0`. Scanopy is pre-1.0
  and documents that breaking API changes can land in any release, so Arborist
  refuses to start outside that range (more in [§8 Troubleshooting](#8-troubleshooting)).
- A Scanopy **user API key** (`Platform > API Keys` in the Scanopy UI, starts
  with `scp_u_`). Reads need a Viewer-permission key; write operations need
  Member or Admin (tag creation specifically needs Admin). **Pitfall:** a key
  created with an empty network list has access to **no** networks, not all of
  them — explicitly select the networks it should see.
- Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/) (or `pip`), to install
  from source.
- If you'll use the HTTP transport (needed to connect from claude.ai, since it
  can't spawn a local process): a way to generate a random token
  (`openssl rand -hex 24` works) for Arborist's own auth gate.

## 3. Installing the `arborist` command

### From source (works today)

```sh
git clone <this-repo>
cd scanopy-arborist-mcp
uv sync
uv run arborist --version    # arborist 0.1.0b1
```

`uv run arborist ...` works from inside the checkout without a separate
install step — every command below that shows `arborist ...` can be read as
`uv run arborist ...` if you haven't installed it as a standalone command. To
install it as a real `arborist` command on your PATH:

```sh
uv tool install .
arborist --version
```

### From a published release (once `OWNER` is filled in and a tag exists)

This is what the README's Quickstart shows, and it'll work as soon as
someone runs the [RELEASE.md](../RELEASE.md) sequence against a real GitHub repo:

```sh
uv tool install git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0
# or: pip install git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0
```

## 4. Deployment

Deployment only matters if you want Arborist running as a standing service
(most useful with the HTTP transport, so multiple clients or a remote
claude.ai session can reach it). If you're only using Claude Code or Claude
Desktop on the same machine as your checkout, stdio needs no deployment at
all — skip to [§6](#6-connecting-it-to-claude).

### Docker Compose — `deploy/docker/`

```sh
cd deploy/docker
cp .env.example .env
# edit .env: SCANOPY_BASE_URL, SCANOPY_API_KEY, ARBORIST_AUTH_TOKEN
docker compose up --build -d
```

`--build` is required today since no image has been pushed to
`ghcr.io/OWNER/scanopy-arborist-mcp` yet; the compose file's `image:` line is
only reachable after that publish step. The container binds `0.0.0.0:60074`
*inside* Docker's network, but the compose file publishes it to the Docker
**host's loopback only** (`127.0.0.1:60074:60074`) — if you widen that
publish, put a TLS-terminating reverse proxy in front and extend
`ARBORIST_ALLOWED_HOSTS` to match.

### Podman Quadlet — `deploy/podman/arborist.container`

Requires podman ≥ 4.6. Before installing, edit `arborist.container`: replace
`OWNER` in the `Image=` line, and point `SCANOPY_BASE_URL` at your instance
(the placeholder `scanopy.example.lan` won't resolve). If you haven't
published an image yet, build and tag one locally first
(`docker build -f deploy/docker/Dockerfile -t <your-tag> .`) and point
`Image=` at that instead.

Create the two secrets **as the user that will run the container**:

```sh
printf %s "<scanopy-api-key>"       | podman secret create scanopy-api-key -
printf %s "$(openssl rand -hex 32)" | podman secret create arborist-gate-token -
```

Install the unit:

```sh
# rootful
sudo mkdir -p /etc/containers/systemd
sudo cp arborist.container /etc/containers/systemd/
sudo systemctl daemon-reload && sudo systemctl start arborist

# rootless
mkdir -p ~/.config/containers/systemd
cp arborist.container ~/.config/containers/systemd/
systemctl --user daemon-reload && systemctl --user start arborist
```

Quadlet units are self-enabling (`[Install] WantedBy=default.target` in the
file) — there's no separate `systemctl enable` step. For rootless to survive
logout and start at boot:

```sh
loginctl enable-linger <user>
```

Verify: `journalctl -u arborist -f` (or `--user`) should show the Scanopy
version handshake, then the HTTP listener line. A quick reachability probe —
an unauthenticated request must come back 401, which proves both the port and
the auth gate are live:

```sh
curl -si http://127.0.0.1:60074/mcp | head -1     # expect: HTTP/1.1 401 Unauthorized
```

Full detail (auto-updates, secret rotation) is in `deploy/podman/README.md`.

### Proxmox LXC — `deploy/lxc/`

`deploy/lxc/ct/arborist.sh` (run on the Proxmox host, creates the container)
and `deploy/lxc/install/arborist-install.sh` (runs inside it) follow the
community-scripts convention. **Hosting caveat that matters today:** this
pair hasn't been merged into community-scripts/ProxmoxVED yet, so
`build.func`'s automated fetch of the install script from their repo won't
find it. Run the ct script from this repo's raw URL instead:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/OWNER/scanopy-arborist-mcp/main/deploy/lxc/ct/arborist.sh)"
```

— which itself needs `OWNER` filled in and pushed before it resolves. Until
then, the practical path is a manual install: create a Debian 13 LXC yourself
and run the commands from `install/arborist-install.sh` starting at
`setup_uv` by hand (substituting a manual `uv` install and a GitHub tarball
download for the community-scripts helper functions it otherwise uses).

The installer deliberately **does not start** the service — it writes
`/opt/arborist/.env` with a freshly generated `ARBORIST_AUTH_TOKEN` and
placeholder `SCANOPY_*` values, then leaves the systemd unit enabled-but-
stopped, because Arborist refuses to start unconfigured. After editing
`/opt/arborist/.env` with your real `SCANOPY_BASE_URL`/`SCANOPY_API_KEY`:

```sh
systemctl restart arborist
journalctl -u arborist -f
```

Full detail in `deploy/lxc/README.md`.

## 5. Configuration reference

Everything is an environment variable. `SCANOPY_*` describes the Scanopy
instance Arborist talks to; `ARBORIST_*` describes Arborist's own behavior.

### The two required variables

| Variable | What it is | You need it because |
|---|---|---|
| `SCANOPY_BASE_URL` | Your Scanopy instance's URL, e.g. `http://scanopy.lan:60072`. Must start with `http://` or `https://`. | Arborist has to know where to send API calls. No default — startup fails without it. |
| `SCANOPY_API_KEY` | A Scanopy **user** API key (`scp_u_...`), from `Platform > API Keys`. | This is Arborist's outbound credential — every read and write goes out under this key's permissions and network scoping. |

### Scoping and connection behavior

| Variable | Default | What it does | You'd want this if... |
|---|---|---|---|
| `SCANOPY_NETWORK_ID` | unset | Pins Arborist to one Scanopy network. List tools default their `network_id` filter to it, and every write is checked against it — resolving a host, service, subnet, or binding by raw UUID from a *different* network is refused, because Scanopy doesn't network-filter UUID lookups server-side. Org-scoped resources (tags) get a tiered policy instead of a simple check — see [§7](#7-what-it-will-refuse-to-do-and-why). | ...you run one Arborist per network/site and want a hard guarantee it can't touch a different one, even if the model gets confused about which network a UUID belongs to. |
| `SCANOPY_TLS_VERIFY` | `true` | Whether to verify Scanopy's TLS certificate. | ...almost never turn this off — it's for talking to a Scanopy behind a self-signed cert during testing. Prefer `SCANOPY_TLS_CA_PATH` for that instead. |
| `SCANOPY_TLS_CA_PATH` | unset | Custom CA bundle for verifying Scanopy's cert. Mutually exclusive with `SCANOPY_TLS_VERIFY=false`. | ...your Scanopy uses a cert from an internal/private CA. |

### The two switches that change what Arborist is *allowed* to do

**`ARBORIST_PROFILE`** (default `readonly`) — this is the main gate. It's not
just a flag Arborist checks per-call: read tools and write tools live in
separate modules, and only the module matching the active profile is
registered with the MCP server at all. A `readonly` Arborist genuinely has no
`update_host_metadata`, `set_host_tags`, `create_tag`, `create_binding`, etc.
for a client to even discover, let alone call — there's no code path where a
prompt-injected or misbehaving client could talk it into writing. Set it to
`readwrite` deliberately, once you've decided you want Claude able to rename
hosts, tag things, and manage bindings.

**`ARBORIST_ENABLE_CONSOLIDATION`** (default `false`) — a second, independent
gate on top of `readwrite`, for exactly one tool: `consolidate_hosts` (merging
two duplicate host records — e.g. the same physical machine discovered twice
because two daemons saw it from different VLANs). Consolidation never edits a
discovered value either; it reassigns which host record *owns* the
interfaces/ports/services, then Scanopy deletes the emptied source record.
That's still sanctioned curation under Arborist's scope boundary — but a
merge has a much bigger blast radius than a rename (it deletes a host record
outright), so it's opt-in separately rather than bundled into `readwrite`.
Setting this without `ARBORIST_PROFILE=readwrite` is a config error at
startup (exit code 2) — consolidation is a write operation and can't exist
under `readonly`.

| Variable | Default | Registers |
|---|---|---|
| `ARBORIST_PROFILE` | `readonly` | `readonly` → 14 read tools. `readwrite` → adds 11 curated-overlay write tools. |
| `ARBORIST_ENABLE_CONSOLIDATION` | `false` | `true` (requires `readwrite`) → adds `consolidate_hosts`. |

### Everything else

| Variable | Default | Used by | Description |
|---|---|---|---|
| `ARBORIST_ALLOW_UNTESTED_VERSION` | `false` | both | Escape hatch for the startup version guard — Arborist starts anyway against an unrecognized Scanopy version, with a loud warning logged. |
| `ARBORIST_TRANSPORT` | `stdio` | CLI | `stdio` or `http`. The `--transport` CLI flag overrides. |
| `ARBORIST_BIND_HOST` | `127.0.0.1` | http | HTTP bind host. `--host` overrides. |
| `ARBORIST_BIND_PORT` | `60074` | http | HTTP bind port. `--port` overrides. |
| `ARBORIST_AUTH_TOKEN` | unset | http | Arborist's own bearer-token gate secret, ≥ 16 characters. Required for HTTP — inbound clients must send `Authorization: Bearer <token>`. Deliberately unrelated to `SCANOPY_API_KEY`; never sent to Scanopy. |
| `ARBORIST_ALLOWED_HOSTS` | unset | http | Comma-separated `Host` header allowlist (DNS-rebinding protection). Required for any non-loopback bind. |
| `ARBORIST_TLS_POSTURE` | `loopback` | http | `loopback` (refuse non-loopback binds), `terminated-upstream` (plain HTTP is fine because something outside Arborist — reverse proxy, container network, tunnel — handles TLS), or `direct` (Arborist serves TLS itself). |
| `ARBORIST_TLS_CERT_PATH` / `ARBORIST_TLS_KEY_PATH` | unset | http | TLS cert/key, required together when posture is `direct`. |

The stdio transport (the default, used by Claude Code/Desktop) only needs the
two required `SCANOPY_*` variables — none of the HTTP-only ones apply.

## 6. Connecting it to Claude

### Claude Code / Claude Desktop (stdio)

This is the simplest path: Claude spawns `arborist` as a subprocess and talks
to it over stdio. No network exposure, no auth token needed.

With `arborist` installed as a command (`uv tool install .` from §3):

```sh
claude mcp add arborist \
  -e SCANOPY_BASE_URL=http://scanopy.lan:60072 \
  -e SCANOPY_API_KEY=scp_u_xxxxxxxx \
  -- arborist
```

Working from the checkout without a separate install:

```sh
claude mcp add arborist \
  -e SCANOPY_BASE_URL=http://scanopy.lan:60072 \
  -e SCANOPY_API_KEY=scp_u_xxxxxxxx \
  -- uv run --directory /path/to/scanopy-arborist-mcp arborist
```

Add `-e ARBORIST_PROFILE=readwrite` to either form to enable the curation
tools (and `-e ARBORIST_ENABLE_CONSOLIDATION=true` on top of that, if you want
host merging too).

For Claude Desktop, the equivalent is `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "arborist": {
      "command": "arborist",
      "args": [],
      "env": {
        "SCANOPY_BASE_URL": "http://scanopy.lan:60072",
        "SCANOPY_API_KEY": "scp_u_xxxxxxxx"
      }
    }
  }
}
```

(Once published, `uvx --from git+https://github.com/OWNER/scanopy-arborist-mcp.git@v0.1.0 arborist`
as the `command`/`args` lets Desktop fetch it on demand with no local install
step at all — see the README Quickstart for that exact form.)

### claude.ai / this chat (Streamable HTTP)

claude.ai can't spawn a local process, so it needs Arborist reachable over the
network as an HTTP MCP connector. Minimum viable setup:

```sh
export SCANOPY_BASE_URL=http://scanopy.lan:60072
export SCANOPY_API_KEY=scp_u_xxxxxxxx
export ARBORIST_AUTH_TOKEN="$(openssl rand -hex 24)"

arborist --transport http
# arborist HTTP transport on 127.0.0.1:60074 (posture=loopback, MCP endpoint: /mcp)
```

That binds loopback only — fine for testing from the same machine
(`claude mcp add --transport http arborist http://127.0.0.1:60074/mcp --header "Authorization: Bearer $ARBORIST_AUTH_TOKEN"`
via Claude Code), but claude.ai runs in Anthropic's cloud and can't reach your
loopback interface at all. To let claude.ai connect, Arborist needs a
publicly (or at least not-loopback) reachable address, which means declaring a
TLS posture and an allowlist:

```sh
export ARBORIST_TLS_POSTURE=terminated-upstream   # a reverse proxy/tunnel handles TLS
export ARBORIST_ALLOWED_HOSTS=arborist.example.com:443
export ARBORIST_BIND_HOST=0.0.0.0
arborist --transport http
```

...with something in front actually terminating TLS and forwarding to
`127.0.0.1:60074` — a reverse proxy (Caddy/nginx/Traefik) if you have a public
host, or a tunnel (Cloudflare Tunnel, Tailscale Funnel) if you don't want to
open a port. `ARBORIST_TLS_POSTURE=direct` is the alternative if you'd rather
Arborist terminate TLS itself (`ARBORIST_TLS_CERT_PATH`/`ARBORIST_TLS_KEY_PATH`).
Either way, Arborist refuses to start at all if you skip this — see the exit
code 4 conditions in [§8](#8-troubleshooting).

Once it's up, add it in claude.ai under connector/MCP settings as a custom
connector: the URL is `https://arborist.example.com/mcp`, with header
`Authorization: Bearer <your ARBORIST_AUTH_TOKEN>`.

## 7. What you can actually ask it

The examples below marked **(live)** were captured 2026-07-08 against a real,
disposable Scanopy 0.17.3 test instance — not invented. The host/tag names
you see (`arborist-stage0-renamed`, `stage0-tag`, `arborist-itest-consol-dest-...`)
are leftovers from earlier build/test sessions on that disposable instance,
not anything special to set up yourself.

### Read-only queries (work in any profile)

> "What hosts do you see on my network?"

calls `list_hosts`, and — **(live)** — on the test instance returns:

```json
{
  "count": 4,
  "offset": 0,
  "hosts": [
    {
      "id": "4294b895-a72c-4eb5-9c15-097de64e1b39",
      "name": "scanopy-daemon",
      "hostname": "docker-desktop",
      "hidden": false,
      "ip_addresses": ["127.0.0.1", "192.168.65.3", "192.168.65.6"],
      "services": [{"name": "Scanopy Daemon", "definition": "Scanopy Daemon"}],
      "open_port_count": 1,
      "tag_ids": []
    },
    {
      "id": "76e25e11-4be0-4599-90e8-2eb1779d8c23",
      "name": "arborist-stage0-renamed",
      "description": "smoke test touch",
      "services": [
        {"name": "Scanopy Server", "definition": "Scanopy Server"},
        {"name": "SSH", "definition": "SSH"},
        {"name": "Gateway", "definition": "Gateway"}
      ],
      "tag_ids": ["988202a8-7104-4ecb-959d-52de4a808298"]
    }
  ]
}
```

> "Show me the topology as a diagram" / "Export the L3 topology"

calls `get_topology` then `export_topology_mermaid` — **(live)**:

```
flowchart TD
    subgraph sub_f12b13af["Remote Network - 0.0.0.0/0"]
        n_882dc667["arborist-itest-consol-dest-111a4fdf<br/>10.99.172.234"]
    end
    subgraph sub_d1d88b99["192.168.65.0/24 - 192.168.65.0/24"]
        n_756cab08["scanopy-daemon<br/>192.168.65.3"]
        n_b5e6cf5f["scanopy-daemon<br/>192.168.65.6"]
        n_025eaaeb["arborist-stage0-renamed<br/>192.168.65.1"]
    end
    n_756cab08 --- n_b5e6cf5f
```

Claude can paste that straight into a Mermaid-rendering surface, or describe
it in prose.

Other things worth asking: "what's running on `<host>`?" (`get_host`), "what
depends on the database service?" (`list_dependencies`), "what tags exist?"
(`list_tags`), "what's on the DMZ subnet?" (`list_subnets` + `list_hosts` with
a filter).

### Write operations, `readwrite` profile

> "Rename `arborist-stage0-renamed` to something clearer and tag it `homelab`."

calls `update_host_metadata` and `set_host_tags`. Both only touch the curated
fields (name/description/hidden/tags) — everything Scanopy discovered about
that host (its real hostname, IPs, ports, services) comes back unchanged in
the same call, because the underlying update is read-modify-write and echoes
discovered fields verbatim.

### Bulk operations — the confirm-before-apply flow

Anything with a wider blast radius (`bulk_update_hosts`, `delete_tag`,
`delete_binding`, `consolidate_hosts`) is two-phase: the first call, without
`confirm=true`, returns a plan and changes nothing. Here's what that actually
looks like — **(live)**, asking to update one host's description without
confirming:

```json
{
  "mode": "plan-only (nothing changed)",
  "plan": [
    {
      "host_id": "76e25e11-4be0-4599-90e8-2eb1779d8c23",
      "host": "arborist-stage0-renamed",
      "changes": {
        "description": {
          "from": "smoke test touch",
          "to": "Docker host, hallway switch uplink"
        }
      }
    }
  ],
  "errors": [],
  "to_apply": 1,
  "next_step": "Call bulk_update_hosts again with confirm=true to apply."
}
```

In conversation, this means Claude will show you the plan and ask before
re-calling with `confirm=true` — it isn't a UI dialog, it's Claude reading the
`next_step` field and treating it as an instruction to check with you first
(the MCP server's own instructions text tells it to). If you say "yes, do it,"
the second call actually applies the change. Nothing happens between those
two calls unless you (or the model, without asking) makes the second one.

### Consolidation, once separately enabled

> "Host X and host Y look like the same machine seen twice — merge them."

calls `consolidate_hosts(destination, source, confirm=false)` first for a
merge preview (what would move, which record gets deleted), same two-phase
pattern as above. Only available when `ARBORIST_ENABLE_CONSOLIDATION=true` is
set on top of `readwrite`.

## 8. What it will refuse to do, and why

These are deliberate design boundaries, not bugs — if Claude tells you it
can't do something in one of these ways, that's Arborist working as intended.

**The discovered layer is never writable, at all.** Hostnames, IPs, MACs,
ports, detected services, interfaces, subnets, VLANs — none of Arborist's
tools can touch these, in any profile. There's no flag that unlocks it. The
curated overlay (name, description, hidden flag, tags, bindings, opt-in
consolidation) is the entire writable surface, and even those writes go
through a path that echoes discovered fields back verbatim rather than
letting a write silently drop or overwrite something Scanopy found.

**`update_tag` and `delete_tag` always refuse outright when `SCANOPY_NETWORK_ID`
is set.** This is the one that surprises people, so it's worth the detail.
Most network-scoped writes (hosts, services, subnets, bindings) are checked by
looking at the *entity's own* `network_id` before the write goes through — but
a tag doesn't have a `network_id`; its label is shared by every entity that
carries it, across every network. Verified live against Scanopy 0.17.3, tags
can also be assigned to **user API keys**, and API-key auth can't read those
back at all (`GET /api/v1/auth/keys` returns 403 "User context required," even
though *assigning* a tag to a key succeeds). That means no scan run under a
scoped Arborist can ever prove a rename or deletion doesn't affect something
outside its configured network — so both operations refuse unconditionally
rather than trust an enumeration that's structurally incomplete. Confirmed
live on the test instance — asking Arborist to recolor a tag while scoped to
a network returns:

```
Refusing to update tag 'stage0-tag': Arborist is scoped to network
679796d0-d76f-473b-9553-3179d6efabcd (SCANOPY_NETWORK_ID) and a tag's label
is shared org-wide — renaming or restyling it changes the label on every
entity carrying it, across every network. That set cannot be verified under
API-key auth (tags on user API keys are unreadable), so a scoped Arborist
cannot prove the change stays in scope. Update tags from an unscoped Arborist
or the Scanopy UI.
```

`create_tag` is fine under a network scope — creating one touches no existing
entity, so there's nothing to leak across. If you need to rename or delete a
tag and you run a network-scoped Arborist, do it from an unscoped instance or
the Scanopy UI instead. Full derivation: `docs/scope-confinement-audit.md`.

**Destructive/bulk operations never apply on the first call.**
`bulk_update_hosts`, `delete_tag`, `delete_binding`, `consolidate_hosts` all
require a second call with `confirm=true`; see [§7](#7-what-you-can-actually-ask-it).
This isn't a refusal exactly, but it means Claude asking "should I go ahead
with this?" mid-conversation is expected behavior, not hesitation.

## 9. Troubleshooting

### Startup refuses with "Scanopy \<version\> is newer/older than..." (exit code 3)

Arborist checks the server's version at startup and refuses to run outside
`>=0.17.2,<0.18.0`, because Scanopy is pre-1.0 and documents that breaking API
changes can land in any release. This is deliberate — an unrecognized version
is treated as a hard failure, not a warning, because Arborist can't know what
changed. Two options: upgrade Arborist to a build verified against your
Scanopy version, or set `ARBORIST_ALLOW_UNTESTED_VERSION=true` to proceed
anyway (Arborist starts, but logs a loud warning on every startup).

### "arborist: cannot reach Scanopy at \<url\>: ..." (exit code 5)

DNS failure, connection refused, or TLS handshake failure. Check
`SCANOPY_BASE_URL` is right and reachable from wherever Arborist runs (a
Docker container needs `host.docker.internal`, not `localhost`, to reach a
Scanopy on the Docker host — see the compose file). If you're using a custom
CA, check `SCANOPY_TLS_CA_PATH`/`SCANOPY_TLS_VERIFY`.

### A tool call fails with "Scanopy API error 401" or "403"

- **401**: `SCANOPY_API_KEY` is missing, wrong, disabled, expired, or API
  access isn't enabled for your Scanopy organization. Keys are managed under
  `Platform > API Keys` in the Scanopy UI, and must be **user** keys
  (`scp_u_...`), not a daemon key.
- **402**: your Scanopy plan doesn't include API access at all (self-hosted
  Community Edition includes it; some cloud plans don't).
- **403**: the key doesn't have permission for that specific operation — reads
  need Viewer, most writes need Member, tag creation needs Admin — or the
  key's network scoping excludes the target. Remember: a key created with an
  **empty** network list has access to *no* networks, not all of them.

### A call is slow, or fails after several retries with a 429 hint

Scanopy rate-limits at 300 requests/minute with a burst of 150. Arborist
retries 429s automatically, honoring `Retry-After` when Scanopy sends one (and
backing off progressively if it doesn't), plus backing off proactively when
`X-RateLimit-Remaining` drops to 3 or fewer — so an occasional slowdown on a
big bulk operation is normal and not a bug. Seeing the 429 error message
itself means retries were exhausted; wait a moment or split the operation into
smaller batches.

### "No host matched '\<selector\>'" or a host you tagged/renamed doesn't resolve by its old ID

Two related things:

- Host lookups accept an id, name, hostname, IP, or MAC — if a raw UUID from
  an earlier listing 404s, Arborist automatically falls back to scanning by
  name/hostname/IP/MAC before giving up, since consolidation deletes the
  source host's ID (see §7). If it still can't find a match, the error
  includes any similarly-named hosts it found, so you're not stuck at a dead
  end.
- If you're looking up a host that was recently merged away by
  `consolidate_hosts`, its old ID is gone permanently — look it up by name, IP,
  or MAC on the surviving (destination) host instead.

### Exit codes, for scripting around startup

| Code | Meaning |
|---|---|
| `2` | Configuration error — missing/invalid env var. The message lists every problem found at once. |
| `3` | Version guard refused the target Scanopy (outside `>=0.17.2,<0.18.0`), and `ARBORIST_ALLOW_UNTESTED_VERSION` wasn't set. |
| `4` | HTTP transport security refused — missing/short `ARBORIST_AUTH_TOKEN`, non-loopback bind without a declared `ARBORIST_TLS_POSTURE`, non-loopback bind without `ARBORIST_ALLOWED_HOSTS`, or `direct` posture missing cert/key. |
| `5` | Scanopy unreachable (DNS, connection refused, TLS handshake, ...). |
