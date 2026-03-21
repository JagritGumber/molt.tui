@echo off
REM Run Molt.tui from Windows (requires bun installed in WSL)
wsl -e bash -c "cd /mnt/d/moltui && bun run start"
