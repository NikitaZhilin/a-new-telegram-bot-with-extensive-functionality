> ARCHIVE NOTICE: This file is historical context only. It is not a current setup, launch, deployment, or security instruction. Use ../README.md, ../USER_GUIDE.md, ../TECHNICAL.md, and ../DEPLOYMENT.md instead.
# VPS Deployment

This deployment is intentionally isolated from other server services such as VPN, MTProto, nginx, and systemd units.
It uses only its own directory, Docker Compose project, containers, network, and volume.

Recommended layout:

```text
/opt/bots/rememberme
```

## 1. Prepare Server

Install Docker and Git on Ubuntu/Debian:

```bash
apt update
apt install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 2. Clone

```bash
mkdir -p /opt/bots
cd /opt/bots
git clone https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality.git rememberme
cd /opt/bots/rememberme
```

## 3. Configure Secrets

```bash
cp .env.example .env
nano .env
```

Set real values on the server only:

```env
BOT_TOKEN=...
BOT_USERNAME=tg_napominalka2_bot
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DB=rememberme
POSTGRES_PORT=15432
POSTGRES_BIND_HOST=127.0.0.1
API_BIND_HOST=127.0.0.1
API_DOCS_ENABLED=false
CORS_ORIGINS=
```

Do not commit `.env`.

`POSTGRES_PORT=15432` is only a localhost port for manual diagnostics from the VPS.
Bot/API/worker containers use the internal Docker hostname `postgres:5432`, so this value does not affect them.
If `15432` is busy, choose another localhost-only port.

## 4. Start

```bash
docker compose --project-name rememberme_bot up -d --build
docker compose ps
docker compose logs -f bot worker
```

## 5. Update

```bash
cd /opt/bots/rememberme
git pull
docker compose --project-name rememberme_bot up -d --build
docker compose logs -f bot worker
```

## 6. Fallback Without Docker Compose

Some VPS images have Docker but no `docker compose` plugin. In that case use the manual deploy script from the project directory:

```bash
cd /opt/bots/rememberme
bash deploy-vps-manual.sh
```

The script:

- pulls the latest git revision;
- synchronizes `.env` database credentials with the existing `rememberme_bot-postgres` container without printing secrets;
- builds app and worker images;
- runs `init-db`;
- recreates only `rememberme_bot-bot`, `rememberme_bot-api`, and `rememberme_bot-worker`;
- leaves VPN, MTProto, nginx, systemd, and unrelated containers untouched.

You can override names if needed:

```bash
PROJECT_DIR=/opt/bots/rememberme \
NETWORK=rememberme_bot_network \
POSTGRES_CONTAINER=rememberme_bot-postgres \
bash deploy-vps-manual.sh
```

## 7. GitHub Actions Deploy

The repository includes `.github/workflows/ci-deploy.yml`.

On every push to `main` it:

- installs dependencies;
- runs the full test suite;
- runs API/bot/worker/all dry-runs;
- deploys to VPS only after tests pass.

Required GitHub Secrets:

```text
VPS_HOST
VPS_USER
VPS_SSH_KEY
VPS_PROJECT_DIR
```

`VPS_PROJECT_DIR` can be omitted if the project lives at `/opt/bots/rememberme`.

The workflow calls:

```bash
cd "$VPS_PROJECT_DIR" && bash deploy-vps-manual.sh
```

Do not store `.env`, bot tokens, database passwords, or admin tokens in GitHub Actions variables unless they are needed by the workflow as encrypted secrets.

## 8. Security Checklist

- Add SSH key access and disable root password login when ready.
- Change the root password after initial setup if it was shared in chat.
- Keep `API_BIND_HOST=127.0.0.1` unless the API is behind HTTPS/proxy.
- Keep `POSTGRES_BIND_HOST=127.0.0.1`; PostgreSQL should not be public.
- Keep `API_DOCS_ENABLED=false` on public VPS.
- Back up the `postgres_data` Docker volume before risky changes.
- Do not change firewall, VPN, MTProto, nginx, or systemd settings for this bot unless you intentionally expose the API.
