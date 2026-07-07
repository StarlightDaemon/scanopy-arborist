#!/usr/bin/env bash
# Headless bootstrap of a fresh Scanopy instance for CI integration tests.
# Creates org/network/user, mints a user API key, and seeds the discovered-
# host stand-in that tests/integration/test_curated_write_safety.py targets.
# Emits SCANOPY_API_KEY / SCANOPY_NETWORK_ID (and appends to $GITHUB_ENV when
# running in Actions).
set -Eeuo pipefail

BASE="${SCANOPY_BASE_URL:-http://localhost:60072}"
JAR="$(mktemp)"
PW="CiBootstrap9-$(openssl rand -hex 8)"

for i in $(seq 1 60); do
  curl -sf "$BASE/api/health" >/dev/null && break
  sleep 2
done

# Setup + register must share one session cookie.
NETWORK_ID=$(curl -sS -c "$JAR" -b "$JAR" -X POST -H 'Content-Type: application/json' \
  -d '{"organization_name":"Arborist CI","network":{"name":"Arborist CI Network"}}' \
  "$BASE/api/auth/setup" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["network_id"])')

curl -sS -c "$JAR" -b "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"email\":\"arborist-ci@example.com\",\"password\":\"$PW\",\"terms_accepted\":true}" \
  "$BASE/api/auth/register" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["success"], d'

USER_JSON=$(curl -sS -c "$JAR" -b "$JAR" -X POST "$BASE/api/auth/me")
USER_ID=$(echo "$USER_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["id"])')
ORG_ID=$(echo "$USER_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["organization_id"])')

API_KEY=$(curl -sS -c "$JAR" -b "$JAR" -X POST -H 'Content-Type: application/json' \
  -d "{\"name\":\"ci\",\"user_id\":\"$USER_ID\",\"organization_id\":\"$ORG_ID\",\"tags\":[],\"permissions\":\"Owner\",\"network_ids\":[\"$NETWORK_ID\"],\"is_enabled\":true,\"expires_at\":null}" \
  "$BASE/api/v1/auth/keys" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["key"])')

# Stand-in for the discovered host the write-safety test targets (a fresh CI
# instance has no scan daemon, so seed a manual host with children).
SUBNET_ID=$(curl -sS -H "Authorization: Bearer $API_KEY" \
  "$BASE/api/v1/subnets?network_id=$NETWORK_ID&limit=200" \
  | python3 -c 'import json,sys; subs=json.load(sys.stdin)["data"]; print(next((s["id"] for s in subs if s.get("subnet_type")=="Remote"), subs[0]["id"]))')
IP_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
PORT_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
curl -sS -H "Authorization: Bearer $API_KEY" -X POST -H 'Content-Type: application/json' \
  -d "{\"name\":\"arborist-stage0-renamed\",\"network_id\":\"$NETWORK_ID\",\"hidden\":false,\"tags\":[],\"description\":\"smoke test touch\",\"ip_addresses\":[{\"id\":\"$IP_ID\",\"subnet_id\":\"$SUBNET_ID\",\"ip_address\":\"10.90.0.10\"}],\"ports\":[{\"id\":\"$PORT_ID\",\"number\":8080,\"protocol\":\"Tcp\"}],\"services\":[]}" \
  "$BASE/api/v1/hosts" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["success"], d'

rm -f "$JAR"
echo "SCANOPY_API_KEY=$API_KEY"
echo "SCANOPY_NETWORK_ID=$NETWORK_ID"
if [ -n "${GITHUB_ENV:-}" ]; then
  {
    echo "SCANOPY_API_KEY=$API_KEY"
    echo "SCANOPY_NETWORK_ID=$NETWORK_ID"
  } >> "$GITHUB_ENV"
fi
