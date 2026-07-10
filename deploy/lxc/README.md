# Arborist LXC (Proxmox VE, community-scripts style)

A [community-scripts/ProxmoxVE](https://github.com/community-scripts/ProxmoxVE)-convention
script pair that creates a Debian 13 LXC on a Proxmox VE host and installs
Arborist into it:

- `ct/arborist.sh` — run on the **Proxmox host**; creates the container
  (1 vCPU / 512 MiB RAM / 3 GB disk, unprivileged) and carries the
  `update_script()` used by later re-runs to update an existing install.
- `install/arborist-install.sh` — runs **inside the container** during
  creation; installs uv, deploys the latest GitHub release to `/opt/arborist`,
  writes `/opt/arborist/.env`, and creates the `arborist` systemd service.

## Usage

On the Proxmox VE host shell:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/StarlightDaemon/scanopy-arborist/main/deploy/lxc/ct/arborist.sh)"
```

Re-running the same command inside an existing Arborist container (or choosing
the update option) runs `update_script()`, which backs up `.env`, deploys the
latest release tarball, re-runs `uv sync --locked --no-dev`, restores `.env`,
and restarts the service.

## Hosting status — read this first

This pair is **written to community-scripts conventions but is not (yet)
hosted by community-scripts**. New scripts must be submitted through their
staging repo, [ProxmoxVED](https://github.com/community-scripts/ProxmoxVED),
and reviewed before they appear in the main repo. Two practical consequences
until that happens:

1. Run the ct script from **this repo's raw URL** (the one-liner above), not
   from a community-scripts URL.
2. `ct/arborist.sh` sources `build.func` from community-scripts, and
   `build.func` fetches the matching `install/<app>-install.sh` **from the
   community-scripts repos** during container creation. Until
   `arborist-install.sh` is merged there, the automated install phase of the
   one-liner will not find it. For a manual install in the meantime: create a
   Debian 13 LXC yourself and run the core steps from
   `install/arborist-install.sh` inside it (everything from `setup_uv`
   downward is plain bash apart from the community-scripts helper functions —
   substitute `uv` installation and a GitHub tarball download by hand).

## What gets installed

- `uv`/`uvx` in `/usr/local/bin` (via community-scripts `setup_uv`).
- The latest `StarlightDaemon/scanopy-arborist` release tarball in `/opt/arborist`,
  with a locked, no-dev virtualenv at `/opt/arborist/.venv`
  (`uv sync --locked --no-dev`).
- `/opt/arborist/.env` (mode 600) containing a freshly generated
  `ARBORIST_AUTH_TOKEN` (48 hex chars, created with `openssl rand` on the
  container at install time) plus placeholder `SCANOPY_*` settings.
- `/etc/systemd/system/arborist.service` — **enabled but not started**.

### Why the service is not started at install time

Arborist deliberately refuses to start until it is configured: it exits
nonzero if `SCANOPY_BASE_URL`/`SCANOPY_API_KEY` are missing or placeholder-
unreachable, and the HTTP transport refuses a `0.0.0.0` bind without
`ARBORIST_ALLOWED_HOSTS`. The usual community-scripts
`systemctl enable -q --now` would therefore always leave a failed unit on
first boot, so the install script only enables the unit and tells you to
start it after configuring. That first failure mode is expected behavior,
not a broken install.

## First configuration

1. Enter the container (`pct enter <ctid>` or SSH) and edit
   `/opt/arborist/.env`:
   - `SCANOPY_BASE_URL` — your Scanopy instance, e.g. `http://scanopy.lan:60072`.
   - `SCANOPY_API_KEY` — a Scanopy **user** API key (Scanopy UI: Platform >
     API Keys; starts with `scp_u_`).
   - `ARBORIST_ALLOWED_HOSTS` — pre-filled with the container IP at install
     time; add a comma-separated DNS name (`arborist.lan:60074`) if your MCP
     clients connect by name (DNS-rebinding protection matches the Host
     header).
   - Optional: `ARBORIST_PROFILE=readwrite` to allow curated writes;
     `ARBORIST_ENABLE_CONSOLIDATION=true` (readwrite only) for host
     consolidation. The default profile is read-only.
2. `systemctl restart arborist`, then check `journalctl -u arborist -f` — a
   healthy start logs the Scanopy version handshake and the HTTP listener on
   port 60074.
3. Point your MCP client at `http://<container-ip>:60074/mcp` with header
   `Authorization: Bearer <ARBORIST_AUTH_TOKEN from .env>`. Quick probe:

   ```bash
   curl -si http://<container-ip>:60074/mcp | head -1   # expect 401 without the token
   ```

## Security notes

- The service binds `0.0.0.0` inside the container and declares
  `ARBORIST_TLS_POSTURE=terminated-upstream`: TLS and exposure control are
  **your** perimeter. Keep port 60074 firewalled to your LAN/VPN, or put a
  TLS-terminating reverse proxy in front — never expose the plain-HTTP port
  to the internet.
- `ARBORIST_AUTH_TOKEN` gates the MCP endpoint and is separate from the
  Scanopy API key on purpose; rotate it by editing `.env` and restarting.
