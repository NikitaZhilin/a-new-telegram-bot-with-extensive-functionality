# Web / App Roadmap

Документ описывает текущее состояние web-версии и реалистичный путь развития в PWA/отдельное приложение.

## Current Status

Implemented:

- server-served web page at `/web`;
- app info endpoint `/app/info`;
- web assets served from `/web/assets/...`;
- user API `/me/...` with read/write operations for lists, reminders, medications, driver vehicles, fuel, expenses, and documents;
- shared-list management endpoints;
- browser auth through Telegram WebApp `initData`;
- personal web key issued in Telegram through `Настройки -> Web-версия`;
- private test login with `ADMIN_TOKEN` + Telegram ID when `WEB_TEST_LOGIN_ENABLED=true`;
- admin UI at `/admin/ui`;
- light/dark theme;
- mobile burger menu;
- testing notice;
- version/changelog information in web summary;
- no known browser-native `prompt/alert/confirm` flows in current web assets.

The web version is functional, but it is still a lightweight integrated client, not a separate frontend application.

## Current Constraints

- Web UI is served by FastAPI as static assets, so frontend complexity should stay moderate.
- Telegram remains the primary notification channel.
- Public use needs HTTPS, domain, strict CORS, and a proxy/firewall model.
- User API auth must remain scoped to one user. Admin endpoints must not be used by the user-facing web UI.
- Medical screens must keep conservative wording: the bot tracks and reminds, it does not prescribe treatment.

## Recommended Next Steps

1. Stabilize current web UI

   - replace remaining browser-native prompts with inline forms;
   - add richer validation messages;
   - improve mobile layout for long lists and action-heavy cards;
   - keep visual parity with Telegram flows.

2. Add export and reporting

   - CSV/PDF export for lists;
   - medication intake history export;
   - driver fuel/expense export;
   - admin activity export.

3. Add PWA shell

   - manifest;
   - installable mobile shortcut;
   - offline-friendly static shell;
   - resilient reload/auth state handling.

4. Consider a separate frontend

   Candidate stack:

   - React or Next.js;
   - TypeScript;
   - TanStack Query;
   - a small component library;
   - same `/me/...` API.

   Keep business logic in Python services. Do not duplicate domain rules in frontend except form validation.

5. Native application later

   A native app is reasonable only after web/PWA and monetization are stable.

   Candidates:

   - Flutter for one consistent UI across iOS/Android;
   - React Native if the web stack is React and shared UI/data patterns are important.

## Monetization Direction

Keep limits in `SubscriptionService`, not in button visibility only.

Possible paid features:

- more shared lists;
- family access;
- extended medication history;
- exports;
- advanced driver statistics;
- long-term activity history;
- multi-user reminder delivery.

## Risks

- Auth mistakes can expose user data.
- Running multiple workers can duplicate notifications.
- Raw activity analytics can become sensitive if message text is stored. Current approach should stay metadata-only.
- Medical and driver data are personal. Treat export, sharing, and admin access carefully.
