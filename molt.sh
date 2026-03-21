#!/usr/bin/env bash
# Run Molt.tui standalone (no zellij)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec bun run start
