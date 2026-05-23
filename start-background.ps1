param(
    [ValidateSet("all", "bot", "api", "worker")]
    [string]$Mode = "all",

    [switch]$RunTests,
    [switch]$SkipDocker,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$runtimeDir = Join-Path $PSScriptRoot ".runtime"
$logsDir = Join-Path $PSScriptRoot "logs"
$pidFile = Join-Path $runtimeDir "rememberme.pid"
$outLog = Join-Path $logsDir "rememberme-background.out.log"
$errLog = Join-Path $logsDir "rememberme-background.err.log"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $existingPid = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existingPid) {
        $existingProcess = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
        if ($existingProcess -and -not $Force) {
            Write-Host "RememberMe already looks running. PID: $existingPid"
            Write-Host "Use .\restart-background.ps1 or .\start-background.ps1 -Force to replace it."
            exit 0
        }
    }
}

if ($Force) {
    & (Join-Path $PSScriptRoot "stop-background.ps1")
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSScriptRoot\start-local.ps1`"",
    "-Mode", $Mode
)

if ($RunTests) {
    $arguments += "-RunTests"
}

if ($SkipDocker) {
    $arguments += "-SkipDocker"
}

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $arguments `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

Set-Content -Encoding ASCII -LiteralPath $pidFile -Value $process.Id

Write-Host "RememberMe started in background. PID: $($process.Id)"
Write-Host "Stdout log: $outLog"
Write-Host "Stderr log: $errLog"
