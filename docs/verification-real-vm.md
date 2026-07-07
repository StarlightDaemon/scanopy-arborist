# Real-VM verification evidence — 2026-07-06

Both container-orchestration artifacts were verified on **real virtual
machines** (Apple Virtualization.framework / applehv, confirmed via
`systemd-detect-virt` → `apple` inside each guest), against the live
disposable Scanopy 0.17.3 instance running on the host. VMs were disposable
and torn down after evidence collection.

## Podman Quadlet (`deploy/podman/arborist.container`)

**Environment:** `podman machine` VM — Fedora CoreOS 44.20260607.3.1,
podman 6.0.0, kernel 7.0.11-200.fc44.aarch64, VM type `applehv`.

```
NAME                     VM TYPE     ...  LAST UP
podman-machine-default*  applehv          Currently running
$ podman machine ssh systemd-detect-virt
apple
```

**Rootless** (user `core`, `loginctl show-user core` → `Linger=yes`; unit at
`~/.config/containers/systemd/arborist.container`, secrets via
`podman secret create scanopy-api-key` / `arborist-gate-token`):

```
● arborist.service - Arborist — MCP server for Scanopy
     Loaded: loaded (/var/home/core/.config/containers/systemd/arborist.container; generated)
     Active: active (running)
arborist INFO connected to Scanopy 0.17.3 (api_version 1) — within supported range >=0.17.2,<0.18.0
arborist INFO arborist HTTP transport on 0.0.0.0:60074 (posture=terminated-upstream, MCP endpoint: /mcp)
POST /mcp without token            → 401
POST /mcp with secret-fed token    → initialize OK, serverInfo arborist 0.1.0b1
```

**Rootful** (unit at `/etc/containers/systemd/arborist.container`, root
storage image, root-side secrets):

```
● arborist.service
     Loaded: loaded (/etc/containers/systemd/arborist.container; generated)
     Active: active (running)
guard + 401 + initialize identical to rootless; serverInfo: arborist 0.1.0b1
```

Notes from this run:
- `/etc/containers/systemd/` does not exist by default on Fedora CoreOS —
  `mkdir -p` first (added to `deploy/podman/README.md`).
- Image names must be lowercase; the `OWNER` placeholder must be replaced
  with a lowercase value (noted in the README callout).

## LXC install script (`deploy/lxc/install/arborist-install.sh`)

**Environment:** Lima VM `arborist-deb` — Debian GNU/Linux 13 (trixie),
systemd 257, kernel 6.12.94+deb13-cloud-arm64, VM type `vz`
(`systemd-detect-virt` → `apple`). This is the closest real-VM equivalent
available on this (ARM) build host: Proxmox VE itself is x86-only, so a PVE
node could not be provisioned. The **actual install script ran verbatim**
under real systemd with one documented substitution:
`fetch_and_deploy_gh_release` deployed the local source tree, since no GitHub
release exists before v0.1.0 is cut.

```
[ok] Installed Arborist            (uv sync — 30 packages incl. scanopy-arborist-mcp 0.1.0b1)
[ok] Configured Arborist           (/opt/arborist/.env, mode 600, install-time token)
[ok] Created Service               (systemctl is-enabled arborist → enabled)

First start with placeholder .env (documented refusal):
  status=5/NOTINSTALLED — "cannot reach Scanopy at http://scanopy.example.lan:60072"

After filling SCANOPY_BASE_URL/SCANOPY_API_KEY:
● arborist.service — Active: active (running)
  arborist INFO connected to Scanopy 0.17.3 (api_version 1) — within supported range >=0.17.2,<0.18.0
  POST /mcp without token → 401; with install-generated token → serverInfo arborist 0.1.0b1
  (ARBORIST_ALLOWED_HOSTS pre-filled with the VM IP worked as shipped)

Reboot persistence (real VM reboot via limactl stop/start):
  up 0 minutes → arborist.service active (running), guard re-passed at boot
```

**Still requiring a real Proxmox VE host** (untestable here): the
`ct/arborist.sh` whiptail/`build.func` flow, `pct` container creation, and
community-scripts' own helper implementations. The install script's full
systemd lifecycle — unit install, enable, documented first-boot refusal,
configure, run, reboot survival — is verified above.

## CI pipeline rehearsal

`.github/workflows/ci.yml` cannot execute before the repo is pushed, so the
integration job's exact steps were rehearsed locally: fresh
`ghcr.io/scanopy/scanopy/server:v0.17.3` + postgres via
`.github/scanopy-ci/docker-compose.yml` (second disposable instance, clean
database), `.github/scanopy-ci/bootstrap.sh` (headless org/network/key/seed),
then `uv run pytest tests/integration -q` → **16 passed** on the fresh
instance.
