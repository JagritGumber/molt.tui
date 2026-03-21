#!/usr/bin/env bash
# Launch Molt.tui workspace in zellij — fire and forget
# Usage: ./launch.sh        (attach in current terminal)
#        ./launch.sh &      (background, free up terminal)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAYOUT="$SCRIPT_DIR/workspace.kdl"
exec zellij --layout "$LAYOUT" attach --create molt-workspace
