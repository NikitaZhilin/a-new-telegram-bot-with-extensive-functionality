# Production deployment

This project deploys as a Docker Compose stack:

- `postgres` stores application data in a Docker volume.
- `init-db` runs Alembic migrations through `python -m src.main init-db`.
- `bot` runs Telegram polling.
- `api` runs FastAPI.
- `worker` sends due reminders.

Do not deploy it as one container unless you intentionally replace the database
and service topology.

The deployment scripts prefer `docker compose` when the plugin is installed.
If the VPS has Docker but no Compose plugin, they fall back to
`deploy-vps-manual.sh`, which recreates only this project's app containers and
keeps the PostgreSQL volume.

Isolation rule for the shared VPS: deployment must only touch resources named
`rememberme_bot-*`, image names `rememberme_bot-*`, network
`rememberme_bot_network`, and volume `rememberme_bot_postgres_data`. Existing
VPN, MTProto, and other bot containers must not be stopped, removed, pruned, or
renamed.

The fallback script enforces this by refusing container names outside the
`rememberme_bot-` prefix and refusing any network except `rememberme_bot_network`.

## Release flow

Automatic release:

```text
developer machine
  -> git push origin main
  -> GitHub Actions
  -> tests and dry-runs
  -> SSH to VPS
  -> clone/fetch/reset project
  -> upload .env.prod from encrypted settings
  -> docker compose build
  -> init-db migrations
  -> restart bot/api/worker
```

Manual release:

```powershell
.\scripts\deploy-vps.ps1 -SshTarget root@SERVER_IP
```

The manual script performs the same server-side steps and copies local
`.env.prod` to the VPS with `scp`.

## GitHub settings

Required GitHub Secrets:

```text
VPS_HOST             VPS host or IP
VPS_USER             SSH user, for example root or deploy
VPS_PORT             SSH port, usually 22
VPS_SSH_KEY          private SSH key allowed to connect to the VPS
BOT_TOKEN            production Telegram bot token
ADMIN_TOKEN          production admin API token
POSTGRES_PASSWORD    production PostgreSQL password
```

Optional GitHub Variables:

```text
DEPLOY_PATH=/opt/bots/rememberme
REPO_URL=https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality.git
COMPOSE_PROJECT_NAME=rememberme_bot
APP_IMAGE=rememberme_bot-app:latest
WORKER_IMAGE=rememberme_bot-worker:latest
POSTGRES_USER=postgres
POSTGRES_DB=rememberme
POSTGRES_PORT=5432
POSTGRES_BIND_HOST=127.0.0.1
API_BIND_HOST=127.0.0.1
API_PORT=8000
API_DOCS_ENABLED=false
CORS_ORIGINS=
BOT_USERNAME=
ADMIN_TELEGRAM_IDS=
WEB_PUBLIC_URL=
WEB_TEST_LOGIN_ENABLED=false
WEB_LOGIN_TOKEN_TTL_DAYS=30
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
APP_VERSION=0.1.0-beta
STARTUP_UPDATE_MESSAGE=Обновлена стабильность сервиса и web-версии.
TESTING_NOTICE_ENABLED=true
TESTING_NOTICE_TEXT=
SEND_STARTUP_MENU_ON_BOOT=true
DEFAULT_SUBSCRIPTION_PLAN=free
WORKER_INTERVAL=60
```

Use Variables for non-secret configuration only. Use Secrets for tokens,
passwords, private keys, and server credentials.

If the repository is private, the HTTPS `REPO_URL` above may not be enough for
`git clone` on the VPS. Use one of these options:

1. Add a read-only deploy key to the GitHub repository and set `REPO_URL` to the
   SSH URL, for example `git@github.com:OWNER/REPO.git`.
2. Use a fine-scoped read-only token in the repo URL only if your security model
   allows it. Prefer a deploy key.

## VPS prerequisites

Ubuntu/Debian example:

```bash
apt update
apt install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

If deployment is not run as `root`, allow the deploy user to use Docker:

```bash
usermod -aG docker deploy
```

Then reconnect SSH so the group membership is applied.

## Production environment

For manual deploy, create a local `.env.prod` from the example:

```powershell
Copy-Item .env.prod.example .env.prod
```

Fill at minimum:

```text
BOT_TOKEN
POSTGRES_PASSWORD
ADMIN_TOKEN
ADMIN_TELEGRAM_IDS
BOT_USERNAME
WEB_PUBLIC_URL, if the API/web UI has a public HTTPS URL
```

Keep production defaults conservative:

```text
POSTGRES_BIND_HOST=127.0.0.1
API_BIND_HOST=127.0.0.1
API_DOCS_ENABLED=false
CORS_ORIGINS=
```

The real `.env.prod` is ignored by Git and must not be committed.

## First automatic deploy

From the project directory, commit the workflow/deployment changes and push to
`main`:

```powershell
git status
git add -A .github/workflows .env.prod.example .dockerignore .gitignore docker-compose.yml docs scripts/deploy-vps.ps1
git commit -m "Add VPS deployment workflow"
git push origin main
```

After push, open GitHub Actions and watch the `Test and deploy` workflow.

Expected deploy stages:

1. Tests run with a PostgreSQL service.
2. `init-db` and dry-runs pass.
3. GitHub Actions connects to VPS by SSH.
4. The VPS repo is cloned or reset to `origin/main`.
5. `.env.prod` is uploaded with mode `600`.
6. Docker images are built.
7. Migrations run through `init-db`.
8. `bot`, `api`, and `worker` are restarted.
9. Service status and recent logs are printed.

If a target VPS has Docker but no `docker compose` plugin, the workflow uses
the fallback path. Installing `docker-compose-plugin` is still recommended for
clearer operations and easier manual checks.

## Manual deploy

Create and fill `.env.prod`, then run:

```powershell
.\scripts\deploy-vps.ps1 -SshTarget root@SERVER_IP
```

Common overrides:

```powershell
.\scripts\deploy-vps.ps1 `
  -SshTarget deploy@SERVER_IP `
  -Port 22 `
  -DeployPath /opt/bots/rememberme `
  -RepoUrl https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality.git `
  -Branch main `
  -EnvFile .env.prod `
  -ComposeProjectName rememberme_bot
```

The script refuses unsafe deploy paths such as `/` and `/opt`.

## VPS checks

```bash
cd /opt/bots/rememberme
git status
docker compose --env-file .env.prod -p rememberme_bot ps
docker compose --env-file .env.prod -p rememberme_bot logs --tail=100 bot
docker compose --env-file .env.prod -p rememberme_bot logs --tail=100 api
docker compose --env-file .env.prod -p rememberme_bot logs --tail=100 worker
docker volume ls | grep rememberme_bot
```

API health check from the VPS:

```bash
curl -fsS http://127.0.0.1:8000/health
```

## Data and backups

Application data is stored in the PostgreSQL Docker volume:

```text
rememberme_bot_postgres_data
```

Do not run `docker compose down -v` in production unless you intend to delete
the database volume.

Backup example:

```bash
docker exec rememberme_bot-postgres pg_dump -U postgres rememberme > /opt/bots/rememberme/backups/rememberme-$(date +%Y%m%d-%H%M%S).sql
```

Restore only after stopping `bot`, `api`, and `worker`, and only into the
intended production database.

## Rollback

Rollback to a known commit:

```bash
cd /opt/bots/rememberme
git fetch origin main
git reset --hard COMMIT_SHA
docker compose --env-file .env.prod -p rememberme_bot build bot api worker init-db
docker compose --env-file .env.prod -p rememberme_bot run --rm init-db
docker compose --env-file .env.prod -p rememberme_bot up -d --no-deps bot api worker
```

Be careful with database migrations: code rollback cannot automatically reverse
schema changes. Take a database backup before risky releases.

## Security checklist

- Do not commit `.env`, `.env.prod`, private keys, tokens, database dumps, logs,
  or backups.
- Do not hardcode server IPs, passwords, bot tokens, or API keys in workflow
  files.
- Keep PostgreSQL bound to `127.0.0.1`.
- Keep the API bound to `127.0.0.1` unless it is behind HTTPS and a firewall.
- Run only one polling bot instance per Telegram token.
- Run only one worker instance to avoid duplicate reminders.
- Use a unique `COMPOSE_PROJECT_NAME` per project on the same VPS.
- Do not run `docker system prune`, `docker container prune`, `docker network
  prune`, or broad `docker rm` commands on the shared VPS during this deploy.
