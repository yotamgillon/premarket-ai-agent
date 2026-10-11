#!/usr/bin/env bash
# One-time bootstrap for a fresh Ubuntu 24.04 EC2 instance.
# Idempotent: safe to run again. Usage (on the instance):
#   bash deploy/ec2/setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/premarket-ai-agent}"
TIMEZONE="${TIMEZONE:-Asia/Jerusalem}"
SWAP_SIZE="${SWAP_SIZE:-2G}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as the normal 'ubuntu' user (the script uses sudo where needed)." >&2
  exit 1
fi

log "Setting system timezone to ${TIMEZONE} (cron schedules use it)"
sudo timedatectl set-timezone "${TIMEZONE}"

log "Adding ${SWAP_SIZE} swap (free-tier instances have only 1 GB RAM)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l "${SWAP_SIZE}" /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
else
  echo "swap already configured"
fi

log "Installing Docker Engine + Compose plugin from Docker's apt repository"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "docker already installed: $(docker --version)"
fi
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

log "Installing make and unattended security upgrades"
sudo apt-get install -y make unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

log "Checking the app directory"
if [[ ! -f "${APP_DIR}/docker-compose.yml" ]]; then
  echo "Clone the repo to ${APP_DIR} first (see docs/DEPLOY_AWS.md, step 5)." >&2
  exit 1
fi
mkdir -p "${APP_DIR}/reports" "${APP_DIR}/logs"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Created ${APP_DIR}/.env from the example. Edit it and add your API key."
fi
chmod 600 "${APP_DIR}/.env"

log "Installing the crontab (weekdays 15:00 ${TIMEZONE})"
sed "s#__APP_DIR__#${APP_DIR}#g" "${APP_DIR}/deploy/ec2/crontab" | crontab -
crontab -l

log "Done. Log out and back in (so the docker group applies), then:"
echo "  cd ${APP_DIR} && nano .env        # add ANTHROPIC_API_KEY"
echo "  make up                            # build, start monitoring, run once"
