# Telegram Mini App TZ

Статус: черновик v1.0, этапы 1-5 выполнены.
Дата: 2026-05-28.

Документ фиксирует техническое задание на превращение текущей web-версии бота в Telegram Mini App. ТЗ описывает целевое поведение, границы MVP, требования к безопасности, UX, backend/API, запуску через Telegram и приемке.

## Источники

Официальные документы Telegram:

- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- Telegram Bot Features: https://core.telegram.org/bots/features
- Telegram Bot API: https://core.telegram.org/bots/api

Локальные документы проекта:

- [User Guide](USER_GUIDE.md)
- [Technical Guide](TECHNICAL.md)
- [Web / App Roadmap](WEB_APP_ROADMAP.md)
- [Deployment](DEPLOYMENT.md)

## Контекст

В проекте уже реализована web-версия:

- `GET /web` - static web shell for standalone web login;
- `GET /miniapp` - the same user shell as Telegram Mini App entrypoint;
- `GET /app/info` - публичная информация о версии;
- `/web/assets/app.js`, `/web/assets/styles.css` - клиентские ассеты;
- `/me/...` - user-scoped API для списков, напоминаний, лекарств, водительского раздела;
- проверка Telegram WebApp `initData` на backend;
- fallback-вход через персональный web-ключ;
- Telegram-кнопки `web_app`, если `WEB_PUBLIC_URL` или `APP_BASE_URL` указывает на HTTPS;
- admin UI отдельно на `/admin/ui`.

Главная задача Mini App - сделать текущий web-клиент основным удобным интерфейсом для сложных пользовательских сценариев, сохранив Telegram-бот как канал уведомлений, быстрых действий и входа.

## Термины

- Bot - существующий Telegram-бот.
- Mini App - web-клиент `/miniapp`, открываемый внутри Telegram через `web_app` кнопку, menu button, main mini app или прямую ссылку. Обычная web-версия остается на `/web`.
- User API - маршруты `/me/...`, доступные только текущему пользователю.
- Admin API - маршруты `/admin/...`, недоступные из пользовательского Mini App.
- MVP - первая production-ready версия Mini App без переписывания frontend-стека.

## Цели

1. Запускать пользовательский web-интерфейс прямо внутри Telegram.
2. Убирать ручной ввод web-ключа при запуске из Telegram за счет `initData`.
3. Сохранить текущую бизнес-логику в Python services/repositories.
4. Дать удобный мобильный интерфейс для разделов:
   - сводка;
   - списки и общие списки;
   - чек-листы;
   - напоминания;
   - лекарства;
   - водитель;
   - информация о версии и настройках.
5. Не раскрывать чужие пользовательские данные и не смешивать user/admin сценарии.
6. Оставить web-ключ как fallback для открытия `/web` вне Telegram.

## Утвержденные Границы MVP

MVP должен включать все текущие пользовательские разделы web-версии:

- сводка;
- списки и общие списки;
- checklist-runs;
- напоминания;
- лекарства;
- водитель: автомобили, заправки, расходы, документы, журнал;
- настройки пользователя, timezone, тариф/подписка, версия/changelog.

Admin UI не входит в пользовательский Mini App. Администрирование остается отдельным интерфейсом `/admin/ui`.

## Не Цели MVP

- Отдельное native-приложение iOS/Android.
- Полная миграция frontend на React/Next.js.
- Attachment menu как основной канал запуска.
- Публичный Mini App Store запуск и платное продвижение.
- Геолокация, биометрия, motion sensors, device storage, secure storage.
- Оплата Telegram Stars, кроме учета будущей совместимости тарифов.
- Групповые collaborative-сценарии внутри чатов, кроме уже существующих общих списков.

## Пользователи И Роли

Обычный пользователь:

- открывает Mini App из бота;
- видит только свои данные и доступные ему общие списки;
- создает и редактирует личные сущности;
- работает с общими списками согласно роли `owner`, `editor`, `viewer`.

Администратор:

- может пользоваться обычными пользовательскими разделами Mini App;
- не получает admin UI внутри пользовательского Mini App;
- открывает admin UI только через отдельный `/admin/ui`.

Гость без Telegram-auth:

- не должен получать доступ к пользовательскому API;
- может видеть только shell и экран входа/fallback-входа.

## Каналы Запуска

### MVP

1. Reply keyboard button `Web-версия`
   - если публичный URL HTTPS настроен, кнопка открывает Mini App через `web_app` напрямую;
   - если HTTPS не настроен, кнопка остается fallback-текстом и выдает web-ключ для `/web`.

2. Inline button `Web-версия`
   - если публичный URL HTTPS настроен, кнопка открывает Mini App через `web_app` напрямую;
   - иначе вызывает текущий сценарий выдачи web-ключа.

3. Menu button
   - настроить через BotFather или Bot API `setChatMenuButton`;
   - URL: `{WEB_PUBLIC_URL}/miniapp`;
   - текст: `RememberMe` или `Web-версия`.

4. Прямая ссылка из бота
   - fallback: `{WEB_PUBLIC_URL}/web?token=...`;
   - используется только когда Mini App не может быть открыт через `initData` или пользователь открывает web вне Telegram.

### После MVP

1. Main Mini App в BotFather
   - включить профильную кнопку запуска;
   - добавить screenshots/video previews;
   - использовать direct link `https://t.me/<bot_username>?startapp`.

2. Deep-link сценарии
   - `startapp=lists`;
   - `startapp=reminders`;
   - `startapp=driver`;
   - `startapp=list_<id>` только после отдельной проверки прав и безопасного парсинга.

## Функциональные Требования MVP

### Авторизация

- При запуске внутри Telegram клиент должен получать `window.Telegram.WebApp.initData`.
- `initData` передается в User API через `X-Telegram-Init-Data`.
- Backend обязан валидировать `initData` по алгоритму Telegram с использованием `BOT_TOKEN`.
- Нельзя использовать `initDataUnsafe` для доверенных решений на сервере.
- Если `initData` отсутствует, разрешается fallback через `X-Web-Login-Token`.
- Web-ключ должен оставаться персональным, ограниченным по TTL и привязанным к пользователю.
- Test login через `ADMIN_TOKEN` должен быть доступен только при `WEB_TEST_LOGIN_ENABLED=true`.

### Инициализация Mini App

- В `src/web/index.html` должен быть подключен Telegram JS SDK в `<head>` до локального `app.js`.
- Клиент должен вызывать `Telegram.WebApp.ready()` после подготовки UI.
- Клиент должен использовать `Telegram.WebApp.expand()` там, где это улучшает основной mobile flow.
- UI должен учитывать `viewportStableHeight`, safe area и Telegram theme params.
- Ошибки запуска должны показываться inline, без `alert`, `prompt`, `confirm`.

### Сводка

- Показывать краткую статистику пользователя.
- Показывать версию, канал релиза и changelog.
- Показывать тестовое предупреждение, если оно включено.
- Не показывать admin-сводку обычному пользователю.

### Списки

- Просмотр доступных списков.
- Создание, переименование, удаление личного списка.
- Добавление, редактирование, удаление пунктов.
- Отметка пунктов.
- Запуск личного checklist-run.
- Завершение, отмена, отметка всех пунктов checklist-run.
- Работа с общими списками по ролям.
- Генерация и отображение share/collaboration-ссылок.

### Напоминания

- Просмотр активных напоминаний.
- Создание напоминания с локальной датой/временем.
- Привязка напоминания к списку.
- Повторы: none, daily, weekly, monthly.
- Выполнение, отмена, удаление.
- Редактирование текста, даты/времени, повтора и привязки к списку.

### Лекарства

- Создание карточки лекарства.
- Редактирование названия, дозировки, инструкции, важности и расписания.
- Отметка `принял` и `пропустил`.
- Архивирование.
- Консервативные медицинские формулировки: учет и напоминания, без советов по лечению.

### Водитель

- Просмотр автомобилей.
- Создание и редактирование авто.
- Использование vehicle presets.
- Заправки: создание, редактирование, удаление.
- Расходы: создание, редактирование, удаление.
- Документы: создание, редактирование, удаление, напоминание до срока.
- Журнал: создание, фильтрация, редактирование, удаление.
- Сводка по расходу, стоимости и документам.

### Настройки

- Показывать пользователя и Telegram ID.
- Показывать тариф/подписку.
- Показывать timezone.
- Показывать информацию о версии.
- Выдачу web-ключа оставить в Telegram-боте, не делать публичную кнопку "создать ключ" внутри Mini App без дополнительной защиты.

## UX Требования

- Mobile-first интерфейс.
- Основные действия должны быть доступны большим touch-friendly controls.
- Цветовая схема должна синхронизироваться с Telegram theme params.
- Светлая/темная тема должна сохраняться как fallback вне Telegram.
- Не использовать браузерные `prompt`, `alert`, `confirm`.
- Не допускать горизонтального скролла на мобильных экранах.
- Длинные названия списков, лекарств, авто и документов не должны ломать layout.
- Ошибки API показываются рядом с действием или в общем inline-message.
- Удаление критичных сущностей требует второго подтверждающего клика.
- Admin-раздел не должен быть частью основной навигации пользовательского Mini App в production.
- Тексты должны быть на русском в MVP.

## Технические Требования

### Frontend

- На MVP оставить текущий static frontend без React/Next.js.
- Файлы:
  - `src/web/index.html`;
  - `src/web/app.js`;
  - `src/web/styles.css`.
- Не дублировать бизнес-правила backend, кроме базовой валидации форм.
- API-запросы выполнять только к same-origin `/me/...`, `/app/info`.
- Admin API не вызывать из пользовательского Mini App.
- Добавить отдельный режим отображения для запуска внутри Telegram:
  - скрыть ручной login panel при валидном `initData`;
  - адаптировать topbar под компактный Telegram viewport;
  - использовать Telegram BackButton там, где это заменяет внутреннюю кнопку "назад".

### Backend

- Сохранить текущий слой:
  - FastAPI routes -> services -> repositories -> db.
- User API остается user-scoped.
- Все операции записи должны повторно проверять ownership/access на backend.
- `get_current_web_user` остается единой точкой авторизации для `/me/...`.
- `USER_AUTH_MAX_AGE_SECONDS` должен быть явно настроен для production.
- Для Mini App не создавать отдельный admin-token based путь.

### Telegram Bot

- `KeyboardButton(..., web_app=WebAppInfo(url=...))` и `InlineKeyboardButton(..., web_app=WebAppInfo(url=...))` использовать только при HTTPS URL.
- При отсутствии HTTPS оставлять fallback выдачи web-ключа.
- Добавить настройку menu button:
  - либо инструкция в deployment;
  - либо команда/скрипт, вызывающий Bot API `setChatMenuButton`.
- Для Main Mini App подготовить BotFather checklist, но не считать это обязательным для MVP.

### Deployment

- Production Mini App должен быть доступен по HTTPS.
- `WEB_PUBLIC_URL` должен быть HTTPS URL без trailing slash.
- API и web должны находиться за reverse proxy/firewall.
- `CORS_ORIGINS` должен быть строгим, без `*` в production.
- `API_DOCS_ENABLED=false` в production.
- PostgreSQL не должен быть публично доступен.
- Запускать только один bot polling instance и один worker instance.

## Безопасность И Приватность

- Доверять только серверной валидации `initData`.
- Не хранить raw `initData` в логах.
- Не логировать тексты пользовательских списков, лекарств, напоминаний и документов.
- Activity analytics остается metadata-only.
- Admin UI и Admin API не должны быть доступны через пользовательскую навигацию Mini App.
- Web-ключи хранить только в хешированном виде.
- Ошибки авторизации не должны раскрывать, существует ли пользователь.
- Для shared lists backend должен проверять роль на каждую операцию.
- Экспорт данных, если появится после MVP, требует отдельного требования на подтверждение и формат.

## Наблюдаемость

- Логировать факт запуска Mini App без чувствительных параметров.
- Разделять события:
  - opened_from_telegram_init_data;
  - opened_with_web_login_token;
  - auth_failed;
  - api_error.
- В admin analytics показывать агрегаты, но не тексты пользовательских данных.

## Критерии Приемки MVP

1. При `WEB_PUBLIC_URL=https://...` кнопка `Web-версия` в Telegram открывает Mini App без ручного web-ключа.
2. Backend принимает `X-Telegram-Init-Data`, валидирует подпись и создает/обновляет пользователя.
3. При невалидном или просроченном `initData` User API возвращает `401`.
4. Вне Telegram `/web` продолжает поддерживать вход по персональному web-ключу.
5. Обычный пользователь не видит admin UI и не может вызвать Admin API через Mini App.
6. Списки, чек-листы, напоминания, лекарства и водительский раздел проходят smoke-тест на мобильной ширине.
7. UI корректно работает в светлой и темной теме Telegram.
8. Нет browser-native `prompt`, `alert`, `confirm`.
9. Тесты `tests/test_web_assets.py` проходят.
10. Dry-run проверки `api`, `bot`, `worker` проходят.
11. Документация deployment содержит шаги BotFather/menu button/HTTPS.

## Этапы Работ

### Этап 1 - Mini App Bootstrap

Статус: выполнено.

- Подключить Telegram JS SDK.
- Улучшить `boot()` для Telegram runtime.
- Скрыть fallback-login при валидном `initData`.
- Добавить Telegram theme/viewport/safe-area integration.
- Добавить тесты на наличие SDK и отсутствие ручного login panel в Telegram mode.

### Этап 2 - Telegram Launch

Статус: выполнено.

- Проверить chooser `Web / приложение` и web_app-вариант при HTTPS.
- Добавить menu button setup в deployment.
- Проверить fallback при HTTP/local.
- Подготовить BotFather checklist.

Реализация:

- reply/inline `Web / приложение` открывают chooser;
- chooser показывает `web_app` вариант Mini App только при HTTPS `WEB_PUBLIC_URL` или `APP_BASE_URL`;
- при HTTP/local остается fallback через персональный web-ключ;
- `python -B -m src.main menu-button --dry-run` проверяет итоговый `{WEB_PUBLIC_URL}/miniapp`;
- `python -B -m src.main menu-button` настраивает Telegram chat menu button через Bot API;
- BotFather/Main Mini App checklist описан в [Deployment](DEPLOYMENT.md).

### Этап 3 - UX Stabilization

Статус: выполнено.

- Убрать admin-раздел из пользовательской навигации production Mini App.
- Полировка мобильной навигации, topbar, длинных карточек.
- Inline loading/error states для основных форм.
- Проверка dark/light theme.

Реализация:

- пользовательская `/web` навигация использует горизонтальные табы без мертвого sidebar toggle;
- admin-раздел убран из пользовательской навигации, администрирование остается в `/admin/ui`;
- login, reload и основные формы получают loading/disabled состояние во время запроса;
- Telegram theme params и standalone light/dark fallback покрыты тестами web assets.

### Этап 4 - Domain Smoke

Статус: выполнено.

- Списки и checklist-run.
- Напоминания с повторами.
- Лекарства и отметки приема.
- Водитель: авто, заправки, расходы, документы, журнал.
- Shared-list роли.

Реализация:

- `tests/test_user_api.py` проверяет `/web`, `/app/info` и основные `/me/...` CRUD-сценарии;
- Mini App API smoke покрывает списки, checklist-run, напоминания, лекарства, водительские авто/заправки/расходы/документы/журнал;
- отдельный API smoke проверяет shared-list роли `owner`, `editor`, `viewer` и недоступность списка для outsider;
- доменные service tests дополнительно покрывают повторы, medication reminders, driver constraints и shared-list role rules.

### Этап 5 - Production Readiness

Статус: выполнено.

- HTTPS reverse proxy.
- Строгий CORS.
- `API_DOCS_ENABLED=false`.
- Проверка логов на отсутствие чувствительных данных.
- Обновление `Deployment`, `User Guide`, `Technical Guide`.

Реализация:

- добавлена команда `python -B -m src.main production-check`;
- команда валидирует HTTPS public URL, отсутствие `/web` и `/miniapp` в base URL, strict CORS, выключенные API docs и test-login;
- команда проверяет допустимый TTL `USER_AUTH_MAX_AGE_SECONDS` и текст Telegram menu button;
- `Deployment` и `Technical Guide` обновлены production-check шагом;
- Mini App launch, menu button и domain smoke закреплены автоматическими тестами.

## Тестирование

Автоматические проверки:

```powershell
python -B -m pytest -p no:cacheprovider tests
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main production-check
```

Ручные проверки:

- открыть Mini App напрямую из reply keyboard;
- открыть Mini App напрямую из inline button;
- открыть `/web` вне Telegram с web-ключом;
- проверить invalid/expired auth;
- проверить мобильный viewport 360px;
- проверить desktop viewport;
- проверить светлую и темную темы Telegram;
- проверить отсутствие доступа к чужому списку по прямому ID;
- проверить, что admin UI недоступен из пользовательской навигации.

## Риски

- Ошибка в auth может раскрыть пользовательские данные.
- Публичный API без строгого reverse proxy/CORS увеличивает поверхность атаки.
- Несогласованность bot-flow и Mini App-flow может путать пользователей.
- Сложный static frontend может стать трудно поддерживаемым без компонентной архитектуры.
- Лекарственные данные чувствительны, формулировки и экспорт требуют аккуратности.
- Несколько worker instances могут дублировать уведомления.

## Решения По Открытым Вопросам

1. Границы MVP: все текущие пользовательские разделы web-версии входят в первый Mini App MVP.
2. Main Mini App в профиле бота не является блокером MVP. Сначала доводится запуск через `web_app` кнопки и menu button, затем включается Main Mini App после smoke-тестов.
3. Admin-раздел должен быть скрыт из пользовательского Mini App. Admin UI остается отдельным `/admin/ui`, не смешивается с `/web`.
4. PWA-установка не входит в первый Mini App MVP. Это следующий этап после стабилизации Telegram Mini App.
5. Monetization через Telegram Stars не входит в MVP. При этом тарифные ограничения должны оставаться в `SubscriptionService`, чтобы позже можно было добавить оплату без переписывания доменной логики.

## Оставшиеся Вопросы Перед Production

1. Утвердить production-домен и публичное имя Mini App.
2. Утвердить текст кнопки menu button: `RememberMe`, `Web-версия` или другое название.
3. Подготовить материалы для BotFather Main Mini App: название, описание, иконка, screenshots/video previews.
4. Решить, нужен ли отдельный staging-домен для тестирования Mini App до production.

## Решение На Текущий Момент

Для этого проекта рациональный путь - не создавать отдельное native-приложение, а использовать существующий web shell как Telegram Mini App на `/miniapp`, сохранив `/web` как обычную web-версию:

- MVP без смены frontend-стека;
- Telegram `initData` как основной вход;
- web-ключ как fallback;
- HTTPS production URL;
- user/admin разделение;
- затем PWA и только после этого отдельный frontend/native app, если появится реальная необходимость.
