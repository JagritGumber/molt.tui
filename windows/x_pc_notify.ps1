param(
  [string]$Title = 'Wyverno X Autopilot',
  [string]$Message = 'Notification'
)

try {
  $wshell = New-Object -ComObject WScript.Shell
  $null = $wshell.Popup($Message, 12, $Title, 64)
} catch {
  $logDir = 'C:\x-agent-debug'
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  Add-Content -Path (Join-Path $logDir 'pc-notify.log') -Value ("[{0}] {1}: {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Title, $Message)
}
