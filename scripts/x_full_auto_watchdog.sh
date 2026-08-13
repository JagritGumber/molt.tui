#!/usr/bin/env bash
set -euo pipefail
cd /mnt/d/moltui
mkdir -p "$HOME/.moltui/cron-logs"
exec "$HOME/.moltui/x-auto-venv/bin/python" agents/x_watchdog.py >> "$HOME/.moltui/cron-logs/x-watchdog.log" 2>&1
