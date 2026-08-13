#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/.moltui/cron-logs"
echo "[$(date '+%F %T')] x_wsl_anchor starting" >> "$HOME/.moltui/cron-logs/x-wsl-anchor.log"
"$HOME/.moltui/x-auto-venv/bin/python" /mnt/d/moltui/agents/x_healthcheck.py --no-drain >> "$HOME/.moltui/cron-logs/x-wsl-anchor.log" 2>&1 || true
while true; do
  sleep 600
  echo "[$(date '+%F %T')] x_wsl_anchor heartbeat" >> "$HOME/.moltui/cron-logs/x-wsl-anchor.log"
done
