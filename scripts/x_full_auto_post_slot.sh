#!/usr/bin/env bash
set -euo pipefail
cd /mnt/d/moltui
mkdir -p "$HOME/.moltui/cron-logs"
exec "$HOME/.moltui/x-auto-venv/bin/python" agents/x_queue_dispatcher.py post >> "$HOME/.moltui/cron-logs/x-post-slot.log" 2>&1
