#!/usr/bin/env bash
set -euo pipefail
cd /mnt/d/moltui
mkdir -p "$HOME/.moltui/cron-logs"
exec "$HOME/.moltui/x-auto-venv/bin/python" agents/x_queue_dispatcher.py scroll >> "$HOME/.moltui/cron-logs/x-scroll-slot.log" 2>&1
