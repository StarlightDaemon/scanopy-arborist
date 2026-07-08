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

## Real Proxmox VE host — 2026-07-07 (closes the gap above)

A genuine **Proxmox VE 8.4.0** node (`pve-manager/8.4.0`, kernel
`6.8.12-9-pve`) was provisioned by booting the official PVE 8.4 auto-install
ISO under QEMU `x86_64` **TCG emulation** on the Apple-silicon build host —
the first time a real PVE node (not a Debian stand-in) was available here.
The earlier installer stall was environmental, not fundamental; the working
recipe is in the session scratchpad `pve/orchestrate.sh`:

- direct kernel boot (`-kernel`/`-initrd`/`-append … proxmox-start-auto-installer
  console=ttyS0,115200`) with the auto-ISO attached as a **USB stick**, not a
  CD-ROM — QEMU does not partition-scan a CD, so the `proxmox-ais` answer
  partition was invisible when booted as a CD (the likely original stall);
- target disk on **AHCI** so it enumerates as `sda`, matching `answer.toml`'s
  `disk-list = ["sda"]`;
- `-cpu max`, `virtio-rng-pci`, `-accel tcg,thread=multi`, `-no-reboot`
  two-phase (install → boot); install completed in ~16 min.

**`ct/arborist.sh` ran through the genuine community-scripts `build.func`**
(fetched from their `main`, `mode=default` preset to skip the whiptail menus)
on this node, with the same two documented substitutions as the Lima run
(install-script URL → in-repo copy; `fetch_and_deploy_gh_release` → local
source tarball). Real outcomes:

```
Using Default Settings … Creating a Arborist LXC using the above default settings
Container ID: 100 · Debian 13 · Unprivileged · 3 GB disk · 1 core · 512 MiB
```

Two environmental blockers surfaced and were handled honestly:
- The fresh-from-ISO node shipped `pve-container 5.2.6`, which rejects the
  Debian 13.1 template (`unsupported debian version '13.1'`). Upgrading the
  container stack from `pve-no-subscription` (→ `pve-container 5.3.5`, what a
  maintained node runs) cleared it; `pct create` then succeeded — real
  unprivileged CT (`features: nesting=1,keyctl=1`, `tags:
  community-script;mcp;network`), Debian 13 template extracted, SSH host keys
  generated.
- QEMU user-mode networking (SLIRP) hands every guest the same `10.0.2.15`
  and does not NAT a second LAN host, so the nested container could not get
  working connectivity via DHCP on `vmbr0` — `build.func`'s "Waiting for
  network" step timed out. This is a **nested-emulation network limitation,
  not an Arborist-script defect**. Worked around with a host-NAT internal
  bridge (`vmbr1` 192.168.100.1/24 + `MASQUERADE` on the PVE node), after
  which the container reached the internet and the host.

The Arborist install steps then ran **inside the real PVE-created LXC**
(`systemd-detect-virt` → `lxc`), verbatim from `arborist-install.sh`
(`setup_uv` → deploy → `uv sync --locked --no-dev` → `.env` → systemd unit →
enable), wired to the live Scanopy 0.17.3:

```
systemd-detect-virt → lxc
arborist INFO connected to Scanopy 0.17.3 (api_version 1) — within supported range >=0.17.2,<0.18.0
arborist INFO arborist tool surface: profile=readonly consolidation=False tools=14
arborist INFO arborist HTTP transport on 0.0.0.0:60074 (posture=terminated-upstream)
POST /mcp without token           → 401
POST /mcp with .env bearer token  → initialize OK, serverInfo arborist 0.1.0b1
```

What remains genuinely unverified anywhere: `build.func`'s automated
"Waiting for network" → in-container install hand-off on a host with
*non-emulated* networking (it works whenever the container can DHCP normally;
it could not be exercised end-to-end here only because SLIRP doesn't nest).
Every Arborist-authored step on both sides of that hand-off is verified.

## CI pipeline rehearsal

`.github/workflows/ci.yml` cannot execute before the repo is pushed, so the
integration job's exact steps were rehearsed locally: fresh
`ghcr.io/scanopy/scanopy/server:v0.17.3` + postgres via
`.github/scanopy-ci/docker-compose.yml` (second disposable instance, clean
database), `.github/scanopy-ci/bootstrap.sh` (headless org/network/key/seed),
then `uv run pytest tests/integration -q` → **16 passed** on the fresh
instance.
