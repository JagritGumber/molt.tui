$ErrorActionPreference = 'Stop'

$task1 = 'Wyverno-X-BrowserBootstrap'
$task2 = 'Wyverno-X-WSLAnchor'
$browserScript = 'D:\moltui\windows\x_browser_bootstrap.ps1'
$wslBatch = 'D:\moltui\windows\x_wsl_anchor.bat'
$user = $env:USERNAME

$trigger1 = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger2.Delay = 'PT30S'

$action1 = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$browserScript`""
$action2 = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$wslBatch`""

$settings1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable
$settings2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable

$principal1 = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$principal2 = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $task1 -Action $action1 -Trigger $trigger1 -Settings $settings1 -Principal $principal1 -Force | Out-Null
Register-ScheduledTask -TaskName $task2 -Action $action2 -Trigger $trigger2 -Settings $settings2 -Principal $principal2 -Force | Out-Null

Write-Output "Registered $task1"
Write-Output "Registered $task2"
