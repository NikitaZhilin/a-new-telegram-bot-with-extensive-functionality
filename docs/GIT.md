# Git Workflow

Документ фиксирует текущий рабочий процесс Git для проекта.

## После Clone

```powershell
Copy-Item .env.example .env
```

Заполните `.env` локальными значениями. Не коммитьте `.env`.

Проверка окружения:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main all --dry-run
```

## Перед Commit

Рекомендуемые проверки:

```powershell
python -B -m pytest -p no:cacheprovider tests
python -B -m src.main all --dry-run
docker-compose config --quiet
```

Для документационных правок достаточно:

```powershell
git diff --check
```

## Commit / Push

```powershell
git status
git add <files>
git commit -m "Meaningful commit message"
git push
```

## Не Коммитить

- `.env`
- `.env.prod`
- `logs/`
- `.runtime/`
- `*.pid`
- `*.db`, `*.sqlite`, `*.sqlite3`
- `__pycache__/`
- database dumps;
- backups;
- tokens, passwords, SSH keys.

