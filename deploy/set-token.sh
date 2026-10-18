#!/usr/bin/env bash
# Save the Discord bot token to .env without it ever showing on screen,
# then (re)start the bot. Usage: bash deploy/set-token.sh
set -euo pipefail
cd "$(dirname "$0")/.."

read -rsp "Paste your bot token (nothing will appear as you paste), then press Enter: " token
echo
token="$(printf '%s' "$token" | tr -d '[:space:]')"
if [[ -z "$token" ]]; then
  echo "No token entered, nothing changed." >&2
  exit 1
fi

[[ -f .env ]] || cp .env.example .env
umask 077
# Replace the DISCORD_TOKEN line (or add one), keeping any other settings.
grep -v '^DISCORD_TOKEN=' .env > .env.tmp || true
printf 'DISCORD_TOKEN=%s\n' "$token" | cat - .env.tmp > .env
rm -f .env.tmp
chmod 600 .env
echo "Token saved to $(pwd)/.env (readable only by you)."

bash deploy/install.sh
