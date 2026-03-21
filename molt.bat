@echo off
REM Run Molt.tui from Windows (requires bun installed in WSL)
wsl -e bash -lc "cd /mnt/d/moltui && bun run start"
