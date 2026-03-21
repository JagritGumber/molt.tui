#!/usr/bin/env bash
# Run Molt.tui from anywhere — auto-detects WSL or native Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec bun run start
