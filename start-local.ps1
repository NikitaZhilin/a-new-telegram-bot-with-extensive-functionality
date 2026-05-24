param(
    [ValidateSet("all", "bot", "api", "worker")]
    [string]$Mode = "all",

    [switch]$SkipDocker,
    [switch]$SkipDryRun,
    [switch]$SkipInitDb,
    [switch]$RunTests,
    [switch]$DryRunOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw ".env was not found. Copy .env.example to .env and fill BOT_TOKEN, ADMIN_TOKEN, POSTGRES_* and DATABASE_URL."
    }

    Get-Content -Encoding UTF8 -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            return
        }

        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Assert-RequiredEnv {
    $missing = @()
    foreach ($name in @("BOT_TOKEN", "ADMIN_TOKEN", "DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) {
            $missing += $name
        }
    }

    if ($missing.Count -gt 0) {
        throw "Missing required .env values: $($missing -join ', ')"
    }

    if ($env:BOT_TOKEN -like "1234567890:*") {
        throw "BOT_TOKEN still looks like a placeholder. Put the real BotFather token into .env."
    }

    if ($env:ADMIN_TOKEN -like "your-*") {
        throw "ADMIN_TOKEN still looks like a placeholder. Put a local secret value into .env."
    }

    if ($env:DATABASE_URL -notlike "postgresql+asyncpg://*") {
        throw "DATABASE_URL must start with postgresql+asyncpg://"
    }
}

function Wait-Postgres {
    param([int]$TimeoutSeconds = 60)

    $containerId = (& docker-compose ps -q postgres) 2>$null
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "PostgreSQL container was not created by docker-compose."
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $status = ""
        try {
            $status = (& docker inspect --format "{{.State.Health.Status}}" $containerId.Trim()) 2>$null
        }
        catch {
            $status = ""
        }

        if ($status -eq "healthy") {
            Write-Host "PostgreSQL container is healthy."
            return
        }

        Start-Sleep -Seconds 2
        Write-Host "." -NoNewline
    } while ((Get-Date) -lt $deadline)

    Write-Host ""
    throw "PostgreSQL did not become healthy within $TimeoutSeconds seconds."
}

Write-Step "Loading .env"
Import-DotEnv -Path ".env"
Assert-RequiredEnv
Write-Host ".env loaded. Secret values are not printed."

if (-not $SkipDocker) {
    Write-Step "Starting PostgreSQL"
    if (-not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
        throw "docker-compose was not found. Install Docker Desktop or run with -SkipDocker if PostgreSQL is already running."
    }

    docker-compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "docker-compose config failed. Check docker-compose.yml and .env syntax."
    }

    docker-compose up -d postgres
    if ($LASTEXITCODE -ne 0) {
        $portHint = [Environment]::GetEnvironmentVariable("POSTGRES_PORT", "Process")
        throw "docker-compose could not start PostgreSQL. Check whether local port $portHint is already in use, or change POSTGRES_PORT and DATABASE_URL in .env."
    }

    Wait-Postgres -TimeoutSeconds 90
}
else {
    Write-Step "Skipping Docker startup"
}

if (-not $SkipInitDb) {
    Write-Step "Initializing database schema"
    python -B -m src.main init-db
}

if ($RunTests) {
    Write-Step "Running tests"
    python -B -m pytest -p no:cacheprovider tests
}

if (-not $SkipDryRun) {
    Write-Step "Running startup dry-run for mode '$Mode'"
    python -B -m src.main $Mode --dry-run
}

if ($DryRunOnly) {
    Write-Step "Dry-run only mode completed"
    Write-Host "Use '.\start-local.ps1 -Mode $Mode' to start the real process."
    exit 0
}

Write-Step "Starting RememberMe in mode '$Mode'"
Write-Host "Press Ctrl+C to stop."
python -B -m src.main $Mode
