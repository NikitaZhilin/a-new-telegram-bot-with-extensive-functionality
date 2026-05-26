# Driver Assistant Changes

Документ фиксирует фактическое состояние driver-раздела в `new_architecture`.

## Что добавлено

- Раздел Telegram-бота "Для водителя".
- Профили автомобилей.
- Журнал заправок по автомобилю.
- Расчет цены за литр, расхода топлива и стоимости километра.
- Учет неполных заправок между полными баками.
- План регулярного ТО по пробегу и по времени.
- Предвыбор популярных автомобилей с базовыми параметрами.
- Быстрые шаблоны списков и авто-напоминаний.
- Ручные расходы: ТО/ремонт, запчасти, мойка, страховка, парковка, штрафы, прочее.
- Документы: ОСАГО/КАСКО, права, диагностика, налог, штраф, прочее.
- Напоминания по документам.
- Экраны расходов и статистики на основе топлива и ручных расходов.
- Шаблонные разделы для жидкостей, запчастей, мойки и шин.

## Основные файлы

Добавлены или существенно задействованы:

- `src/bot/handlers/driver.py` - Telegram handlers, wizard-сценарии, разделы driver-меню.
- `src/bot/states/driver.py` - состояния driver wizard.
- `src/services/driver_service.py` - бизнес-логика авто, ТО и заправок.
- `alembic/versions/003_driver_schema.py` - базовая схема driver-таблиц.
- `alembic/versions/004_driver_quality_constraints.py` - manual mileage baseline и CHECK constraints.
- `alembic/versions/008_driver_expenses_documents.py` - ручные расходы и документы.
- `alembic/versions/009_vehicle_presets.py` - расширенные поля авто для presets.
- `alembic/versions/010_driver_document_reminders.py` - связь документов с напоминаниями.
- `tests/test_driver_service.py` - сервисные тесты driver-логики.
- `tests/test_driver_inputs.py` - тесты парсеров, FSM cleanup и driver reminder template.

Изменены для интеграции:

- `src/bot/app.py` - регистрация driver handlers/conversations.
- `src/bot/keyboards/builder.py` - driver keyboards.
- `src/bot/handlers/navigation.py` - `/start`, `/help`, главное меню.
- `src/bot/handlers/reminders.py` - старт авто-напоминаний из шаблонов.
- `src/services/settings_service.py` - driver-статистика пользователя.
- `src/api/routes/admin.py` - driver overview в `/admin/users/{id}/records`.
- `src/db/models/models.py` - ORM-модели `DriverVehicle`, `DriverFuelEntry`.

## Callback prefixes

- `driver_menu`
- `driver_section:*`
- `driver_list_template:*`
- `driver_reminder_template:*`
- `driver_vehicle_create`
- `driver_vehicle_edit:*`
- `driver_vehicle_view:*`
- `driver_vehicle_delete:*`
- `driver_vehicle_delete_confirm:*`
- `driver_vehicle_mileage:*`
- `driver_fuel_add:*`
- `driver_fuel_edit:*`
- `driver_fuel_full:*`
- `driver_fuel_history:*`
- `driver_fuel_view:*`
- `driver_fuel_delete:*`
- `driver_fuel_delete_confirm:*`
- `driver_expense_add`
- `driver_expense_edit:*`
- `driver_expense_view:*`
- `driver_expense_delete:*`
- `driver_expense_delete_confirm:*`
- `driver_expense_category:*`
- `driver_expense_vehicle:*`
- `driver_document_add`
- `driver_document_edit:*`
- `driver_document_view:*`
- `driver_document_delete:*`
- `driver_document_delete_confirm:*`
- `driver_document_type:*`
- `driver_document_vehicle:*`
- `driver_document_remind:*`
- `driver_service_view:*`
- `driver_service_done:*`

## Схема таблиц

`driver_vehicles`:

- владелец `user_id`;
- название, марка, модель, год;
- `manual_mileage_km` - ручной базовый пробег;
- `current_mileage_km` - расчетный текущий пробег;
- интервалы ТО по километрам и месяцам;
- последнее ТО по пробегу и дате;
- CHECK constraints на неотрицательный пробег и положительные интервалы.

`driver_fuel_entries`:

- владелец `user_id`;
- автомобиль `vehicle_id`;
- пробег заправки;
- литры, сумма, цена за литр;
- полный/неполный бак;
- АЗС/комментарий;
- расчетный расход и стоимость километра;
- CHECK constraints на положительные литры/стоимость и неотрицательный пробег.

`driver_expenses`:

- владелец `user_id`;
- необязательная связь с автомобилем `vehicle_id`;
- название, категория, сумма;
- дата расхода;
- комментарий;
- CHECK constraint на положительную сумму.

`driver_documents`:

- владелец `user_id`;
- необязательная связь с автомобилем `vehicle_id`;
- название и тип документа;
- дата окончания;
- количество дней для предварительного напоминания;
- связь с созданными напоминаниями;
- CHECK constraint на неотрицательное количество дней.

## Тесты

Текущее состояние общего тестового набора после актуализации проекта: `113 passed`.

Driver-блок покрыт тестами:

- создание/редактирование/удаление авто;
- обновление пробега;
- добавление/редактирование/удаление заправок;
- пересчет расхода после изменения истории;
- защита ownership;
- отклонение некорректных значений на уровне сервиса;
- пересчет `current_mileage_km` после редактирования/удаления максимальной заправки;
- очистка driver FSM context;
- старт авто-напоминания из шаблона;
- регистрация callback-префиксов.

## Риски и ограничения

- Разделы "Жидкости", "Запчасти", "Мойка", "Шины" пока работают как шаблоны/идеи для быстрых списков и напоминаний.
- Документы и ручные расходы заведены отдельными сущностями, но их визуальная аналитика еще проще, чем топливная статистика.
- `manual_mileage_km` введен для корректного пересчета текущего пробега после изменений топливной истории.
- Перед production-миграциями нужен backup базы.

## Следующие шаги

- Добавить историю шин и сезонную замену.
- Добавить экспорт расходов.
- Добавить audit log для критичных изменений журнала.
- Расширить аналитику расходов по категориям и периодам.
