$tasks = @('Wyverno-X-BrowserBootstrap','Wyverno-X-WSLAnchor')
foreach ($task in $tasks) {
  Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Removed $task"
}
