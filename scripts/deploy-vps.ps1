param(
    [Parameter(Mandatory = $true)]
    [string]$SshTarget,

    [int]$Port = 22,

    [string]$DeployPath = "/opt/bots/rememberme",

    [string]$RepoUrl = "https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality.git",

    [string]$Branch = "main",

    [string]$EnvFile = ".env.prod",

    [string]$ImageName = "rememberme_bot-app:latest",

    [string]$WorkerImageName = "rememberme_bot-worker:latest",

    [string]$ContainerName = "rememberme_bot-bot",

    [string]$ComposeProjectName = "rememberme_bot",

    [string]$ProjectResourcePrefix = "rememberme_bot"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "ssh was not found in PATH."
}

if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp was not found in PATH."
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Production env file was not found: $EnvFile. Create it from .env.prod.example and keep it out of Git."
}

if ([string]::IsNullOrWhiteSpace($DeployPath) -or $DeployPath -eq "/" -or $DeployPath -eq "/opt") {
    throw "Refusing unsafe DeployPath: $DeployPath"
}

if ($ComposeProjectName -ne $ProjectResourcePrefix) {
    throw "Refusing ComposeProjectName '$ComposeProjectName'. Expected '$ProjectResourcePrefix' on this shared VPS."
}

if (-not $ContainerName.StartsWith("$ProjectResourcePrefix-")) {
    throw "Refusing ContainerName '$ContainerName'. Expected prefix '$ProjectResourcePrefix-'."
}

function ConvertTo-ShellSingleQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    ssh -p $Port $SshTarget $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed with exit code $LASTEXITCODE."
    }
}

$quotedDeployPath = ConvertTo-ShellSingleQuoted $DeployPath
$quotedRepoUrl = ConvertTo-ShellSingleQuoted $RepoUrl
$quotedBranch = ConvertTo-ShellSingleQuoted $Branch
$quotedComposeProjectName = ConvertTo-ShellSingleQuoted $ComposeProjectName
$quotedImageName = ConvertTo-ShellSingleQuoted $ImageName
$quotedWorkerImageName = ConvertTo-ShellSingleQuoted $WorkerImageName
$quotedContainerName = ConvertTo-ShellSingleQuoted $ContainerName
$quotedProjectResourcePrefix = ConvertTo-ShellSingleQuoted $ProjectResourcePrefix

$prepareCommand = @"
set -e
DEPLOY_PATH=$quotedDeployPath
REPO_URL=$quotedRepoUrl
BRANCH=$quotedBranch

if [ -z "`$DEPLOY_PATH" ] || [ "`$DEPLOY_PATH" = "/" ] || [ "`$DEPLOY_PATH" = "/opt" ]; then
  echo "Refusing unsafe DEPLOY_PATH: `$DEPLOY_PATH" >&2
  exit 1
fi

command -v git >/dev/null 2>&1 || { echo "git is required on the VPS." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker is required on the VPS." >&2; exit 1; }

if [ -d "`$DEPLOY_PATH/.git" ]; then
  git -C "`$DEPLOY_PATH" fetch origin "`$BRANCH"
  git -C "`$DEPLOY_PATH" checkout "`$BRANCH"
  git -C "`$DEPLOY_PATH" reset --hard "origin/`$BRANCH"
else
  mkdir -p "`$(dirname "`$DEPLOY_PATH")"
  git clone --branch "`$BRANCH" "`$REPO_URL" "`$DEPLOY_PATH"
fi

mkdir -p "`$DEPLOY_PATH/logs" "`$DEPLOY_PATH/backups"
"@

Write-Host "Updating repository on VPS..."
Invoke-Remote -Command $prepareCommand

Write-Host "Uploading production environment..."
scp -P $Port $EnvFile "$SshTarget`:$DeployPath/.env.prod"
if ($LASTEXITCODE -ne 0) {
    throw "scp failed with exit code $LASTEXITCODE."
}
Invoke-Remote -Command "chmod 600 $quotedDeployPath/.env.prod"

$deployCommand = @"
set -e
DEPLOY_PATH=$quotedDeployPath
COMPOSE_PROJECT_NAME=$quotedComposeProjectName
APP_IMAGE=$quotedImageName
WORKER_IMAGE=$quotedWorkerImageName
CONTAINER_NAME=$quotedContainerName
PROJECT_RESOURCE_PREFIX=$quotedProjectResourcePrefix

cd "`$DEPLOY_PATH"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_PROJECT_NAME="`$COMPOSE_PROJECT_NAME" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" build bot api worker init-db

  COMPOSE_PROJECT_NAME="`$COMPOSE_PROJECT_NAME" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" up -d postgres

  COMPOSE_PROJECT_NAME="`$COMPOSE_PROJECT_NAME" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" rm -f -s init-db >/dev/null 2>&1 || true

  COMPOSE_PROJECT_NAME="`$COMPOSE_PROJECT_NAME" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" run --rm init-db

  COMPOSE_PROJECT_NAME="`$COMPOSE_PROJECT_NAME" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" up -d --no-deps bot api worker

  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" ps
  docker compose --env-file .env.prod -p "`$COMPOSE_PROJECT_NAME" logs --tail=80 bot api worker
  docker logs --tail=80 "`$CONTAINER_NAME" 2>/dev/null || true
else
  echo "Docker Compose plugin is not available; using deploy-vps-manual.sh fallback."
  ENV_FILE=.env.prod \
  PROJECT_RESOURCE_PREFIX="`$PROJECT_RESOURCE_PREFIX" \
  PROJECT_DIR="`$DEPLOY_PATH" \
  APP_IMAGE="`$APP_IMAGE" \
  WORKER_IMAGE="`$WORKER_IMAGE" \
  bash deploy-vps-manual.sh
fi
"@

Write-Host "Building images, running migrations, and restarting services..."
Invoke-Remote -Command $deployCommand
