param(
    [ValidateSet("all", "bot", "api", "worker")]
    [string]$Mode = "all",

    [switch]$RunTests,
    [switch]$SkipDocker
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

& (Join-Path $PSScriptRoot "stop-background.ps1")

$parameters = @{
    Mode = $Mode
    Force = $true
}
if ($RunTests) {
    $parameters.RunTests = $true
}
if ($SkipDocker) {
    $parameters.SkipDocker = $true
}

& (Join-Path $PSScriptRoot "start-background.ps1") @parameters
