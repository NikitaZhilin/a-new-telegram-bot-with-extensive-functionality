Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$runtimeDir = Join-Path $PSScriptRoot ".runtime"
$pidFile = Join-Path $runtimeDir "rememberme.pid"

function Stop-ProcessTree {
    param([int]$RootPid)

    $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $RootPid }
    foreach ($child in $children) {
        Stop-ProcessTree -RootPid $child.ProcessId
    }

    $process = Get-Process -Id $RootPid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $RootPid -Force
        Write-Host "Stopped process $RootPid ($($process.ProcessName))."
    }
}

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "No RememberMe PID file found. Checking for stale project processes."
}
else {
    $pidText = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($pidText) {
        Stop-ProcessTree -RootPid ([int]$pidText)
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$projectPath = $PSScriptRoot.Replace("\", "\\")
$staleProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like "*$PSScriptRoot*") -or
    ($_.CommandLine -like "*$projectPath*") -or
    ($_.CommandLine -like '* -m src.main all*') -or
    ($_.CommandLine -like '* -m src.main bot*') -or
    ($_.CommandLine -like '* -m src.main api*') -or
    ($_.CommandLine -like '* -m src.main worker*')
}

foreach ($processInfo in $staleProcesses) {
    if ($processInfo.ProcessId -ne $PID) {
        Stop-ProcessTree -RootPid $processInfo.ProcessId
    }
}

Write-Host "RememberMe background processes stopped."
