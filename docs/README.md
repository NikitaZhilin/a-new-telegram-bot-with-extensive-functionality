# Project Documentation

This directory contains the current documentation for `new_architecture`.

## Current Documents

- [User Guide](USER_GUIDE.md) - how to use the Telegram bot and web version.
- [Technical Guide](TECHNICAL.md) - architecture, runtime modes, data flow, tests, and operational notes.
- [Driver Guide](DRIVER.md) - vehicle journal, fuel, expenses, documents, and driver-specific backend notes.
- [Deployment](DEPLOYMENT.md) - VPS/Docker/GitHub Actions deployment.
- [Git Workflow](GIT.md) - local Git checks and commit hygiene.
- [Web Roadmap](WEB_APP_ROADMAP.md) - web/PWA/app development direction.
- [Archive](archive/) - historical implementation reports and old provider-specific notes. Every archived file starts with an archive notice.

## Documentation Rules

- Do not put real `.env` values, tokens, passwords, private keys, server IPs, or personal paths into docs.
- Keep launch instructions in [README.md](../README.md) and [Deployment](DEPLOYMENT.md).
- Historical implementation reports in `archive/` are not launch instructions.
- If code behavior changes, update the relevant document in the same change.
