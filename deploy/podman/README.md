# Arborist on Podman (Quadlet)

`arborist.container` is a [Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
unit: drop it into a systemd generator directory and systemd runs Arborist as a
native service — no `podman generate systemd`, no hand-written unit files.

Requires **podman >= 4.6** (Quadlet with `Secret=...,type=env`). Verify with
`podman --version`.

Before installing, edit `arborist.container`:

- `Image=` — ships pointing at `ghcr.io/starlightdaemon/scanopy-arborist-mcp`;
  change it if you're building/publishing your own fork's image.
- `SCANOPY_BASE_URL` — point at your Scanopy instance (the placeholder
  `http://scanopy.example.lan:60072` will not resolve).
- Uncomment the optional `ARBORIST_PROFILE` / `SCANOPY_NETWORK_ID` /
  `ARBORIST_ENABLE_CONSOLIDATION` lines as needed. The default profile is
  `readonly`; consolidation additionally requires `ARBORIST_PROFILE=readwrite`.

## 1. Create the secrets

Two Podman secrets are injected as environment variables at runtime. Create
them **as the same user that will run the container** (root for rootful,
your user for rootless):

```sh
# The Scanopy user API key Arborist authenticates outbound with:
printf %s "<scanopy-api-key>" | podman secret create scanopy-api-key -

# Arborist's own inbound HTTP bearer token (>= 16 chars; NOT a Scanopy credential):
printf %s "$(openssl rand -hex 32)" | podman secret create arborist-gate-token -
```

Keep a copy of the gate token wherever your MCP client is configured — clients
must send `Authorization: Bearer <token>` to `http://127.0.0.1:60074/mcp`.

Check they exist: `podman secret ls`

## 2a. Install — rootful

```sh
sudo mkdir -p /etc/containers/systemd   # not present by default on Fedora CoreOS
sudo cp arborist.container /etc/containers/systemd/
sudo systemctl daemon-reload
sudo systemctl start arborist
sudo systemctl status arborist
```

Note there is no `systemctl enable` step: Quadlet-generated units are enabled
via the `[Install] WantedBy=default.target` line in the `.container` file and
start on boot automatically.

## 2b. Install — rootless

```sh
mkdir -p ~/.config/containers/systemd
cp arborist.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start arborist
systemctl --user status arborist
```

For the service to start at boot (rather than at first login) and survive
logout, enable lingering for the user:

```sh
loginctl enable-linger <user>
```

## 3. Auto-updates (optional)

`AutoUpdate=registry` labels the container so `podman auto-update` will pull a
newer `:latest` and restart the service — but only if the timer is running:

```sh
sudo systemctl enable --now podman-auto-update.timer     # rootful
systemctl --user enable --now podman-auto-update.timer   # rootless
```

Dry-run to see what would be updated: `podman auto-update --dry-run`

## 4. Verify

Check that Quadlet accepts the unit (prints the generated `arborist.service`;
add `--user` for rootless):

```sh
/usr/lib/systemd/system-generators/podman-system-generator --dryrun
```

Check the service and container:

```sh
systemctl status arborist          # or: systemctl --user status arborist
journalctl -u arborist -f          # or: journalctl --user -u arborist -f
podman ps --filter name=arborist
```

On startup the log should show Arborist connecting to Scanopy (the §5.4
version gate) and then
`arborist HTTP transport on 0.0.0.0:60074 (posture=terminated-upstream, MCP endpoint: /mcp)`.

Probe the endpoint from the host — an unauthenticated request must be rejected
with 401, which proves both that the port is reachable and that the bearer
gate is active:

```sh
curl -si http://127.0.0.1:60074/mcp | head -1     # expect: HTTP/1.1 401 Unauthorized
curl -si -H "Authorization: Bearer <gate-token>" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"ping"}' \
  http://127.0.0.1:60074/mcp | head -1            # expect: HTTP/1.1 200 OK
```

## Security notes

- `PublishPort=127.0.0.1:60074:60074` keeps Arborist loopback-only. If you
  widen it, put TLS in front (that is what
  `ARBORIST_TLS_POSTURE=terminated-upstream` declares) and extend
  `ARBORIST_ALLOWED_HOSTS` with the public host:port your clients will use.
- Secrets never appear in the unit file, the image, or `podman inspect`;
  rotate one with `podman secret rm <name>` + recreate + restart the service.
