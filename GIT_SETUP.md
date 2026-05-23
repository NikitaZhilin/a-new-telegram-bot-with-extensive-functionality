# Git Setup

This project is prepared so local secrets, runtime files, logs, caches, and local databases stay out of Git.

## First Publish

Run from this directory:

```powershell
git init
git branch -M main
git add .
git status
git commit -m "Initial RememberMe bot architecture"
git remote add origin <YOUR_REPOSITORY_URL>
git push -u origin main
```

Replace `<YOUR_REPOSITORY_URL>` with a GitHub/Gitea/GitLab SSH or HTTPS URL.

## After Clone

```powershell
Copy-Item .env.example .env
```

Fill `.env` locally. Do not commit it.

Then run:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main all --dry-run
.\start-local.ps1
```

## Before Commit

Recommended checks:

```powershell
python -B -m pytest -p no:cacheprovider tests
python -B -m src.main all --dry-run
docker-compose config --quiet
```

## Never Commit

- `.env`
- `logs/`
- `.runtime/`
- `*.pid`
- `*.db`, `*.sqlite`, `*.sqlite3`
- `__pycache__/`
