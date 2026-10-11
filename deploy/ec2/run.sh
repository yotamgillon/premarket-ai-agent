#!/usr/bin/env bash
# Called by cron. Runs the agent once and appends its JSON logs to a monthly file.
# The agent itself exits early on weekends and NYSE holidays.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${APP_DIR}"
mkdir -p logs
LOG_FILE="logs/agent-$(date +%Y-%m).log"

# flock: if a previous run is somehow still going, don't start a second one.
exec 9>"${APP_DIR}/logs/.run.lock"
if ! flock -n 9; then
  echo "$(date -Is) previous run still in progress, skipping" >>"${LOG_FILE}"
  exit 0
fi

APP_UID="$(id -u)"
APP_GID="$(id -g)"
export APP_UID APP_GID
# Make sure the monitoring stack is up (no-op if it already is).
docker compose up -d pushgateway prometheus grafana >>"${LOG_FILE}" 2>&1
docker compose run --rm agent "$@" >>"${LOG_FILE}" 2>&1
