param(
    [string]$TaskName = "RememberMe Telegram Bot",
    [switch]$AtStartup,
    [switch]$RunTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$script = Join-Path $PSScriptRoot "start-background.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Mode all"
if ($RunTests) {
    $arguments += " -RunTests"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $PSScriptRoot

if ($AtStartup) {
    $trigger = New-ScheduledTaskTrigger -AtStartup
}
else {
    $trigger = New-ScheduledTaskTrigger -AtLogOn
}

$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "RememberMe Telegram bot local autostart" `
    -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName"
Write-Host "Trigger: $(if ($AtStartup) { 'At system startup' } else { 'At user logon' })"
Write-Host "To run now: Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "To remove: Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
