#!/usr/bin/env bash
set -u

CONTROL_SSH_HOST="${CONTROL_SSH_HOST:-172.16.224.4}"
CONTROL_SSH_PORT="${CONTROL_SSH_PORT:-22}"
CONTROL_SSH_USER="${CONTROL_SSH_USER:-zhang_jun}"
CONTROL_SSH_KEY="${CONTROL_SSH_KEY:-/run/secrets/hydro/id_ed25519_hydro_control}"
LOCAL_AGENT_PORT="${LOCAL_AGENT_PORT:-28080}"
LOCAL_MINIO_PORT="${LOCAL_MINIO_PORT:-29000}"

while true; do
  ssh -N -T \
    -i "${CONTROL_SSH_KEY}" \
    -p "${CONTROL_SSH_PORT}" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${LOCAL_AGENT_PORT}:127.0.0.1:18080" \
    -L "127.0.0.1:${LOCAL_MINIO_PORT}:127.0.0.1:19000" \
    "${CONTROL_SSH_USER}@${CONTROL_SSH_HOST}"
  sleep 5
done
