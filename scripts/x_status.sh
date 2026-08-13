#!/usr/bin/env bash
set -euo pipefail
cd /mnt/d/moltui
exec "$HOME/.moltui/x-auto-venv/bin/python" agents/x_autopilot_status.py
