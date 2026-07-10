#!/usr/bin/env bash
source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)
# Copyright (c) 2021-2026 community-scripts ORG
# Author: StarlightDaemon
# License: MIT | https://github.com/community-scripts/ProxmoxVE/raw/main/LICENSE
# Source: https://github.com/StarlightDaemon/scanopy-arborist

APP="Arborist"
var_tags="${var_tags:-mcp;network}"
var_cpu="${var_cpu:-1}"
var_ram="${var_ram:-512}"
var_disk="${var_disk:-3}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources

  if [[ ! -d /opt/arborist ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  if check_for_gh_release "arborist" "StarlightDaemon/scanopy-arborist"; then
    msg_info "Stopping Service"
    systemctl stop arborist
    msg_ok "Stopped Service"

    msg_info "Backing up Configuration"
    cp /opt/arborist/.env /opt/arborist.env
    msg_ok "Backed up Configuration"

    fetch_and_deploy_gh_release "arborist" "StarlightDaemon/scanopy-arborist" "tarball" "latest" "/opt/arborist"

    msg_info "Updating Arborist"
    cd /opt/arborist
    $STD uv sync --locked --no-dev
    msg_ok "Updated Arborist"

    msg_info "Restoring Configuration"
    mv /opt/arborist.env /opt/arborist/.env
    msg_ok "Restored Configuration"

    msg_info "Starting Service"
    systemctl start arborist
    msg_ok "Started Service"
    msg_ok "Updated successfully!"
  fi
  exit
}

start
build_container
description

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Arborist is an MCP server (Streamable HTTP). Point your MCP client at:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:60074/mcp${CL}"
echo -e "${INFO}${YW}It refuses to start until configured: set SCANOPY_BASE_URL, SCANOPY_API_KEY${CL}"
echo -e "${INFO}${YW}and ARBORIST_ALLOWED_HOSTS in /opt/arborist/.env, then 'systemctl restart arborist'.${CL}"
echo -e "${INFO}${YW}MCP clients authenticate with the generated ARBORIST_AUTH_TOKEN from that file.${CL}"
