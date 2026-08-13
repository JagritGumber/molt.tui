#!/usr/bin/env bash
set -euo pipefail
cd /mnt/d/moltui
mkdir -p "$HOME/.moltui/cron-logs"
exec "$HOME/.moltui/x-auto-venv/bin/python" agents/x_mission_loop.py >> "$HOME/.moltui/cron-logs/x-mission-loop.log" 2>&1
