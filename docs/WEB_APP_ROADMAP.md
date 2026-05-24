# Web / App roadmap

Current web status:

- `/web` is implemented as a lightweight server-served web site.
- `/me/...` includes read and write endpoints for core lists, reminders, medications, and driver journal flows.
- Browser auth supports Telegram WebApp `initData`; private testing can use `ADMIN_TOKEN` + Telegram ID when `WEB_TEST_LOGIN_ENABLED=true`.
- The next web improvements are UX polish, inline editing, exports, HTTPS/domain setup, and a dedicated PWA shell.

Документ описывает практичный путь развития бота в web-кабинет и отдельное приложение без переписывания текущей архитектуры.

## Текущая база

- `bot` уже является клиентом к общей бизнес-логике.
- `services` и `repositories` можно переиспользовать из API.
- `api` уже существует, но сейчас он в основном административный.
- `db` хранит доменные сущности отдельно: списки, напоминания, лекарства, автомобильный журнал, подписки, активность.

## Рекомендуемая последовательность

1. User API

   Базовые read-only endpoints уже добавлены:

   - `GET /me`
   - `GET /me/summary`
   - `GET /me/lists`
   - `GET /me/reminders`
   - `GET /me/medications`
   - `GET /me/driver`

   Текущая реализация покрывает `GET /me`, `GET /me/summary`, `GET /me/lists`,
   `GET /me/reminders`, `GET /me/medications`, `GET /me/driver`.
   Следующий шаг - добавить write endpoints после стабилизации web UI.

   Важно: не давать frontend прямой доступ к admin endpoints.

2. Авторизация

   MVP-авторизация уже заложена через Telegram WebApp `initData`.
   Для внешней PWA вне Telegram нужно добавить отдельный login-flow:

   - Telegram Login Widget для web;
   - deep-link из бота с одноразовым login token;
   - короткоживущий web session/JWT;
   - все запросы scoped by `user_id`.

3. PWA-кабинет

   Первый web-интерфейс лучше делать как PWA:

   - быстрее, чем нативное приложение;
   - можно закрепить на экран телефона;
   - единая кодовая база;
   - Telegram остается каналом уведомлений.

   Стек-кандидат: Next.js + TypeScript + TanStack Query + простая компонентная библиотека.

4. Монетизация

   Ограничения стоит держать не в кнопках, а в `SubscriptionService`.

   Возможные платные функции:

   - больше общих списков;
   - семейный доступ;
   - расширенная история лекарств;
   - экспорт PDF/CSV;
   - автомобильная статистика за периоды;
   - web-кабинет;
   - напоминания нескольким участникам.

5. Нативное приложение

   Имеет смысл после PWA и платежной модели.

   Кандидаты:

   - Flutter, если нужен один качественный UI для iOS/Android;
   - React Native, если web будет на React и хочется шарить часть логики.

## Узкие места

- Нужна аккуратная auth-модель, иначе web откроет чужие данные.
- Нужно решить, где будут push-уведомления: Telegram-only или отдельные mobile push.
- Нужно ввести audit/activity retention, чтобы таблица событий не росла бесконечно.
- Для семейных/общих данных нужно заранее определить роли: owner/editor/viewer.
- Для медицинских данных нужна осторожная формулировка: бот напоминает и фиксирует, но не дает медицинских назначений.

## Ближайший технический шаг

Сделать слой `src/api/routes/me.py` и использовать существующие сервисы. Это даст основу для PWA без копирования бизнес-логики из bot handlers.
