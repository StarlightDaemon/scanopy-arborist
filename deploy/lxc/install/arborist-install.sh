#!/usr/bin/env bash

# Copyright (c) 2021-2026 community-scripts ORG
# Author: StarlightDaemon
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://github.com/StarlightDaemon/scanopy-arborist

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

USE_UVX="YES" setup_uv
fetch_and_deploy_gh_release "Arborist" "StarlightDaemon/scanopy-arborist" "tarball" "latest" "/opt/arborist"

msg_info "Installing Arborist"
cd /opt/arborist
$STD uv sync --locked --no-dev
msg_ok "Installed Arborist"

msg_info "Configuring Arborist"
# Arborist's own inbound bearer token — generated fresh on this machine at
# install time, never shipped in the release or this script.
ARBORIST_AUTH_TOKEN="$(openssl rand -hex 24)"
cat <<EOF >/opt/arborist/.env
# Arborist — MCP server for Scanopy (curates names/tags/visibility; never
# touches scanner-discovered data). After editing: systemctl restart arborist

### - Target Scanopy instance — REQUIRED, fill these in before first start
SCANOPY_BASE_URL=http://scanopy.example.lan:60072
SCANOPY_API_KEY=scp_u_xxxxxxxxxxxxxxxx
## - optional: pin Arborist to a single Scanopy network id
# SCANOPY_NETWORK_ID=

### - Arborist's own inbound HTTP bearer token (generated at install time).
### - NOT a Scanopy credential. MCP clients send 'Authorization: Bearer <token>'.
ARBORIST_AUTH_TOKEN=${ARBORIST_AUTH_TOKEN}

### - Transport hardening
## - LXC binds 0.0.0.0; restrict exposure at your firewall/proxy
ARBORIST_TLS_POSTURE=terminated-upstream
## - REQUIRED for the 0.0.0.0 bind (DNS-rebinding protection): comma-separated
## - Host header values your MCP clients will use. Pre-filled with this
## - container's IP; add a DNS name if your clients connect by name.
ARBORIST_ALLOWED_HOSTS=${LOCAL_IP}:60074

### - Tool profile (default: read-only)
ARBORIST_PROFILE=readonly
## - uncomment for curated writes (rename/describe/hide hosts, tags, bindings):
# ARBORIST_PROFILE=readwrite
## - uncomment to also enable host consolidation (requires readwrite):
# ARBORIST_ENABLE_CONSOLIDATION=true
EOF
chmod 600 /opt/arborist/.env
msg_ok "Configured Arborist"

msg_info "Creating Service"
cat <<EOF >/etc/systemd/system/arborist.service
[Unit]
Description=Arborist MCP server for Scanopy
After=network-online.target

[Service]
WorkingDirectory=/opt/arborist
EnvironmentFile=/opt/arborist/.env
ExecStart=/opt/arborist/.venv/bin/arborist --transport http --host 0.0.0.0 --port 60074
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
# Deliberate deviation from the usual `systemctl enable -q --now`: Arborist
# refuses to run until the operator fills SCANOPY_BASE_URL/SCANOPY_API_KEY in
# /opt/arborist/.env (exit 5 "cannot reach Scanopy" with the placeholder URL,
# exit 2 if the values are removed entirely). Starting it now would only
# leave a failed unit on first boot, so we enable it and let the operator do
# the first start after configuring.
systemctl enable -q arborist
msg_ok "Created Service"
msg_ok "First start is manual: edit /opt/arborist/.env, then run 'systemctl restart arborist'"

motd_ssh
customize
cleanup_lxc
