@echo off
REM Launch Molt.tui: Alacritty -> WSL -> Zellij -> workspace
start "" "alacritty.exe" --title "Molt.tui" -e wsl bash -lc "/home/jagrit/.cargo/bin/zellij --layout /mnt/d/moltui/workspace.kdl attach --create molt-workspace"
