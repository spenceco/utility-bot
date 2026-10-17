#!/usr/bin/env bash
# Install or update utility-bot as a systemd service. Run from the project folder:
#   bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .
mkdir -p data logs   # must exist: the service may only write here

if [[ -f .env ]]; then
  chmod 600 .env      # the token is readable by this user only
else
  echo "No .env yet: copy .env.example to .env and add DISCORD_TOKEN, then rerun." >&2
fi

sudo cp deploy/utility-bot.service /etc/systemd/system/utility-bot.service
sudo systemctl daemon-reload
sudo systemctl enable utility-bot.service

if [[ -f .env ]]; then
  sudo systemctl restart utility-bot.service
  sleep 3
  systemctl --no-pager --lines=0 status utility-bot.service || true
  echo "Logs: journalctl -u utility-bot -f"
fi
