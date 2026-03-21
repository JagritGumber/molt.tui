# Launch Molt.tui workspace — fire and forget
# Starts Alacritty + Zellij with Molt.tui in the first pane
$zellij = "/home/jagrit/.cargo/bin/zellij"
$layout = "/mnt/d/moltui/workspace.kdl"
$cmd = "$zellij --layout $layout attach --create molt-workspace"
Start-Process "alacritty.exe" -ArgumentList "--title Molt.tui -e wsl bash -lc '$cmd'" -WindowStyle Hidden
