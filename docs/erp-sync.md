# Модуль «ERP-синхронизация» (дни рождения + отсутствия сотрудников)

> **Когда читать:** задача касается импорта `birth_date`/`gender` или отсутствий
> из ERP-выгрузки, mailbox-поллинга, FIO-матчинга, отчётов админу.
> **Ключевой код:** `backend/app/services/erp_sync/`, `backend/app/worker/tasks/erp_sync.py`,
> `backend/app/worker/tasks/erp_absences_sync.py`, `backend/app/api/erp_sync/`.
> **Миграции:** `087`–`090` (дни рождения), `092` (отсутствия).
> **Планы фич:** [`./wip/erp-sync.md`](./wip/erp-sync.md) (дни рождения),
> [`./wip/erp-absences.md`](./wip/erp-absences.md) (отсутствия).

## Суть

Модуль принимает **два потока** отчётов от ERP (1С) на общий служебный ящик,
опрашиваемый по IMAP (cron):

1. **Дни рождения** — отчёт «Справочник: Сотрудники» (ФИО, дата рождения, пол).
   Портал сопоставляет ФИО с `users.full_name` и записывает `birth_date` + `gender`
   в `users` (перетирание). Данные видны всем авторизованным в карточке `/staff`.
2. **Отсутствия** — отчёт «Кадровая история сотрудников за период» (ФИО,
   должность, подразделение, состояние, начало, окончание). Портал сопоставляет
   ФИО и ведёт ranged-записи в `erp_absences` (отпуск/отгул/болезнь/командировка)
   с **full-replace** при каждом импорте. Отображение отсутствий — в разработке
   (виджет «кого нет на неделе», карточка сотрудника).

Общие для обоих потоков: IMAP-ящик (ADR-048), mailbox/matcher/report-инфраструктура,
cron-паттерн (distributed-lock + interval-guard + watchdog + probe), multi-channel
уведомления (email + in-app + Grafana), ручной запуск (mailbox-trigger + multipart-upload).

## Архитектура (pipeline)

```
ERP (2×/нед email) → общий ящик → [ARQ-cron run_erp_sync / ручной запуск]
   → aioimaplib SEARCH ALL → post-fetch фильтр (subject+sender+attachment)
       ├─ подходит   → обработать (дедуп по message_id в БД защищает от повтора)
       └─ мимо фильтра → пропустить
   → attachment → parser (txt/csv/xlsx/xls via xlrd, auto-encoding BOM→cp1251)
   → rows[FIO, date, gender]
   → dedup по нормализованному ФИО:
       ├─ одинаковые во всех полях  → 1 запись (норма 1С — несколько должностей)
       └─ разные дата/пол при том же ФИО → конфликт[] (НЕ пишем)
   → per-row matcher (reuse users_repo.find_by_full_name_exact → words):
       ├─ 1 match  → UPDATE birth_date+gender (всегда) + diff в report.changed
       ├─ 0 match  → unmatched[]
       └─ >1 match → ambiguous[] (НЕ пишем)
   → commit (в той же транзакции: erp_sync_runs + email_outbox + notification)
   → post-commit: SSE-publish in-app уведомлений
   → при delete_after_fetch: STORE \Deleted + EXPUNGE успешно импортированных писем
   → health-probe: integration:health['erp_sync'], erp_sync:last_success_at
[watchdog cron /day]: if now - last_success > expected_interval × 1.5 → alert
```

### Источник файла абстрагирован

`importer.run_import(Attachment)` — единая точка. `Attachment` (`{filename,
data, hash}`) наполняется mailbox-циклом или multipart-upload endpoint'ом —
логика импорта/матчинга/отчёта общая.

## Схема БД

**Миграция 087** (`users` + 2 таблицы):

- `users.birth_date DATE NULL` + `users.gender VARCHAR(10) NULL`
  (CHECK `male/female`) — видны всем авторизованным.
- `erp_sync_runs` — лог каждого импорта: `message_id` UNIQUE (дедуп писем),
  `triggered_by` (`cron`/`manual`), `status` (`success`/`partial`/`failed`/
  `skipped`), счётчики (`rows_*`, `conflicts`, `errors`), `report JSONB`
  (changed/unmatched/ambiguous/conflicts/errors для email-отчёта).
- `erp_sync_settings` — singleton (`id=1`): `imap_*` + `imap_password_enc`
  (Fernet, write-only), `poll_interval_seconds` (CHECK 60–3600, default 900),
  `expected_interval_days` (default 4, для watchdog), `notify_emails` (override).

**Миграция 088** (additive `ALTER TABLE erp_sync_settings`):

- `poll_enabled BOOL` (default false) — отдельный флаг авто-поллинга. Двойной
  гейтинг: `modules.erp_sync.enabled` (вся фича) AND `poll_enabled` (только
  авто-забор). Позволяет выключить поллинг, оставив ручной upload.
- `mail_subject_filter` / `mail_sender_filter` / `mail_attachment_filter`
  (VARCHAR, nullable) — CI-подстроки для post-fetch фильтрации на общем ящике.

**Миграция 090** (additive `ALTER TABLE erp_sync_settings`):

- `delete_after_fetch BOOL` (default false) — удалять письма из общего ящика
  после успешного импорта (`STORE +FLAGS \Deleted` + `EXPUNGE`, клон
  `helpdesk_mailbox_settings.delete_after_fetch`). Default off: удаление на
  общем ящике необратимо, админ включает осознанно. Дедуп по `message_id`
  (UNIQUE) защищает от повторной обработки и без удаления.

## Парсер (`services/erp_sync/parser.py`)

Поддерживаемые форматы (по расширению):

- `txt` / `tsv` / `csv` — tab/`;`/`,`-separated, авто-кодировка
  (BOM → `charset_normalizer` → cp1251 fallback). Реальный кейс: один из
  приложенных файлов был cp1251 — хардкод utf-8 сломался бы молча.
- `xlsx` / `xlsm` — через `openpyxl` (уже в deps).
- `xls` (legacy OLE2, Excel 97-2003) — через `xlrd==2.0.1` (dep ради этого
  формата; заморожен, ломаться нечему).

Ожидаемая структура: 3 колонки — ФИО, дата рождения (`ДД.ММ.ГГГГ`), пол
(`Мужской`/`Женский`). Заголовок-«Параметры:» и служебные строки фильтруются
автоматически (по непарсимости даты во 2-й колонке).

**Нормализация ФИО:** trim + обрезка скобок-примечаний (`Зубайрова ... (Сухорукова
с 01.09.2021)` → `Зубайрова ...`) + `ё→е` + lower. Обрезка скобок критична: без
неё точный матч ломается.

**Дедуп + конфликты:** группировка по нормализованному ФИО. Идентичные во всех
полях → 1 запись (норма 1С — несколько должностей). Разные дата/пол при том же
ФИО → конфликт (однофамилец? ошибка выгрузки?) → **не пишем**, в отчёт.

## Matcher (`services/erp_sync/matcher.py`)

Переиспользует готовый FIO-матчер из `app.api.users.users_repo` (его же юзает
модуль meetings): `find_by_full_name_exact` → при 0 `find_by_full_name_words`
(по словам в любом порядке, с ё→е и раскладкой). Triage по `len(matches)`:
1 → Matched, >1 → Ambiguous (не пишем), 0 → Unmatched.

## Импорт (`services/erp_sync/importer.py`)

`run_import(db, redis, *, attachment, message_id, triggered_by) -> ErpSyncRun`:

1. Дедуп по `message_id` (только для mailbox; upload всегда новый).
2. Парсинг → per-row матчинг → UPDATE + diff (источник истины ERP: перетираем
   всегда; diff пустой, если значения не изменились).
3. Сборка JSONB-отчёта (с лимитами `_MAX_REPORT_ITEMS=200` для размера).
4. `INSERT erp_sync_runs`.
5. Уведомления (email + in-app) в той же транзакции (outbox-паттерн).
6. `commit` → post-commit SSE-publish.

`status`: `success` (нет проблем) / `partial` (есть unmatched/ambiguous/
conflicts/errors) / `failed` (файл целиком не распарсился).

## Mailbox (`services/erp_sync/mailbox.py`)

Клон паттерна `helpdesk/ingress.py` + post-fetch фильтрация (IMAP `SEARCH
SUBJECT` ненадёжен с MIME/B-encoded кириллицей). Берёт **`SEARCH ALL`**, а не
`UNSEEN`: ящик общий, его читают люди, и любое прочитанное письмо получает
`\Seen` — опираться на `UNSEEN` значило бы терять письма после первого
открытия ящика (реальный баг на проде, фикс 2026-08-01). Маркер «обработано» —
дедуп по `Message-ID` в `erp_sync_runs` (UNIQUE), не почтовый флаг. Портал
**не** ставит `\Seen` и не трогает письма мимо фильтра — не портит чужой
inbox на общем ящике. `probe_imap_connection` — для `POST /erp-sync/test`.

`delete_messages(email_settings, uids)` — опциональное удаление отработанных
писем (`delete_after_fetch`, миграция 090): `STORE +FLAGS \Deleted` per-UID +
`EXPUNGE`, новое подключение после fetch-сессии. Удаляются только успешно
импортированные письма (при ошибке письмо остаётся для повтора/разбора);
дедуп по `message_id` удержит повтор и без удаления. Клон паттерна
`helpdesk_mailbox_settings.delete_after_fetch`.

## Worker (`worker/tasks/erp_sync.py`)

- `run_erp_sync(ctx, triggered_by='cron')` — module-gate (`modules.erp_sync.enabled`)
  AND `poll_enabled` → interval-guard (`erp_sync:imap:last_poll_at`,
  `poll_interval_seconds`) → distributed-lock (`erp_sync:imap:poll_lock`, Lua
  compare-and-delete) → `fetch_unread_attachments` → `run_import` per письмо.
  Manual-запуск (`triggered_by='manual'`) обходит poll-gate.
- `erp_sync_watchdog(ctx)` — раз в день (09:00). Если последний успешный импорт
  старше `expected_interval_days × 1.5` → email + in-app алерт админам.
- `probe_erp_sync()` — integration-health probe: `None` (модуль/poll off) /
  `True` (свежий) / `False` (протух). Метрика
  `portal_integration_up{integration="erp_sync"}`.

Cron-регистрация: `run_erp_sync` каждые 15 мин (`minute={0,15,30,45}`),
`erp_sync_watchdog` раз в день (`hour=9, minute=0`).

## API (`api/erp_sync/`)

Все endpoints гейтируются `require_erp_sync_module` (deps.py) + `AdminDep`.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/erp-sync/settings` | Текущие настройки (write-only password) |
| `PUT` | `/erp-sync/settings` | Обновление (IMAP + фильтры + poll_enabled + notify_emails) |
| `POST` | `/erp-sync/test` | Проверка IMAP-подключения (login + select) |
| `POST` | `/erp-sync/run` | Mailbox-trigger: ставит ARQ-задачу `run_erp_sync(manual)` |
| `POST` | `/erp-sync/import-file` | Multipart-upload файла → синхронный `run_import` |
| `GET` | `/erp-sync/runs` | История импортов (пагинация, report в ответе) |
| `GET` | `/erp-sync/runs/{id}` | Один run |

## Настройка (admin)

1. Включить модуль: `PUT /admin/modules/erp_sync` `{enabled: true}`.
2. Сконфигурить ящик: `PUT /erp-sync/settings` — IMAP host/port/ssl/
   username/password(write-only)/folder, `poll_interval_seconds`,
   `expected_interval_days`, `notify_emails` (override; null = все admin с
   `notify_email=true`).
3. Задать фильтры (для общего ящика): `mail_subject_filter` (напр. «Сотрудники»),
   `mail_sender_filter` (email ERP), `mail_attachment_filter` (имя/расширение).
4. (Опц.) Включить `delete_after_fetch` — удалять отработанные ERP-отчёты из
   общего ящика. По умолчанию off: письма остаются (дедуп по `message_id`
   защищает от повторной обработки и без удаления).
5. Проверить: `POST /erp-sync/test`.
6. Включить поллинг: `poll_enabled: true`.
7. При желании — загрузить файл вручную: `POST /erp-sync/import-file`
   (для первичной верификации парсера, без mailbox).

## Уведомления админу

- **Email** — `enqueue_outbox_email(KIND_GENERIC)` per адресат (из
  `notify_emails` или все admin). HTML-отчёт с разделами
  changed/unmatched/ambiguous/conflicts/errors + diff old→new. Отправляет
  существующий cron `process_email_outbox` (каждые 10 c) через общий SMTP-контур.
- **In-app** (колокольчик) — `create_notification(type='erp_sync_report')`
  всем admin с `notify_inapp=true`. SSE-publish post-commit.
- **Grafana/health** — `portal_integration_up{integration="erp_sync"}` из
  integration_health probe. Watchdog-алерт — отдельный тип `erp_sync_watchdog`.

## Грабли / контекст

- **Раздел «Email» = только SMTP** (нет IMAP). Входящая почта — per-feature
  singleton (как `helpdesk_mailbox_settings`). Настройки приёма ERP живут в
  `erp_sync_settings`; отправка отчётов — через общий SMTP.
- **Общий ящик = обязательная фильтрация.** Без фильтра импорт сломается на
  чужом письме. Портал не ставит `\Seen` и не трогает письма мимо фильтра —
  маркер «обработано» это дедуп по `Message-ID` в БД, а не почтовый флаг
  (фикс 2026-08-01: `SEARCH UNSEEN` молча терял письма, как только ящик
  открывали и все письма становились `\Seen`).
- **`users.full_name` — одна свободная строка** из Keycloak, порядок слов не
  гарантируется. Матчинг через `find_by_full_name_words` (любой порядок).
- **`xlrd==2.0.1`** — только `.xls`; `.xlsx` читает `openpyxl`. Не путать.
- **Russian TLS (Минцифры)**: `aioimaplib` использует системный trust store
  (`ssl.create_default_context`), сертификат `russian_trusted_root_ca.crt`
  уже в образе.
- **`related_resource_type="erp_sync_run"`** в outbox, но `related_resource_id`
  не передаём (run.id — bigint, не UUID; несём в `payload.erp_sync_run_id`).
- **POST /erp-sync/run использует короткое имя** `enqueue_job("run_erp_sync")`,
  НЕ FQN (AGENTS.md). Cron-регистрация — FQN-строка (асимметрия ARQ).

---

## Поток «Отсутствия» (миграция 092)

Второй поток ERP — отпуска/отгулы/болезни/командировки. Отчёт 1С «Кадровая
история сотрудников за период» приходит отдельным письмом со своими фильтрами
(`mail_absences_*`). Полный план и архитектурные решения — в
[`./wip/erp-absences.md`](./wip/erp-absences.md).

### Схема БД (отсутствия)

- **`erp_absences`** — ranged-записи: `user_id` (FK CASCADE, NOT NULL), `kind`
  (7-enum: vacation_main/vacation_extra/unpaid_leave/sick/business_trip/
  day_off_paid/day_off_unpaid), `position`, `department`, `start_date`/`end_date`
  (CHECK end≥start), `source` ('erp_sync'|'manual'). Индексы: `(user_id)` и
  `(start_date, end_date)` для range-запросов виджета «кого нет на неделе».
- **`erp_absences_runs`** — клон `erp_sync_runs` (отдельный лог + дедуп по
  `message_id`), поле `rows_inserted` вместо `rows_updated`.
- **Расширение `erp_sync_settings`** — `absences_poll_enabled`, 3 фильтра
  (`mail_absences_*`), `absences_expected_interval_days` (default 7).

### Парсер (`services/erp_sync/absences_parser.py`)

Иерархическая структура (в отличие от 3 фиксированных колонок дней рождения):
шапка → заголовок колонок → блоки «ФИО-строка + N строк-периодов». Алгоритм —
линейный проход с «текущим сотрудником»: строка без даты = сотрудник, строка с
датой = период. Маппинг «Состояние»→`kind` через contains-матчинг (порядок в
`_KIND_MAP` важен: «отпуск неоплачиваемый» ловим раньше «отпуск основной»).
Дедуп по `(fio_norm, kind, start, end)`. Общие хелперы декодирования — в
`parser_utils.py` (вынесены из `parser.py`, поведение 1:1).

### Импорт (`services/erp_sync/absences_importer.py`) — full-replace

Ключевое отличие от дней рождения (per-field upsert): **full-replace**. Каждый
отчёт самодостаточен (содержит весь период — обычно год), поэтому перед вставкой:
`DELETE FROM erp_absences WHERE source='erp_sync'` → `INSERT` matched. Старые
записи исчезнувших сотрудников стираются автоматически.

**Безопасность failed-файла**: при 0 валидных matched-строк (битый файл / пустой)
БД **не трогается** — иначе одно кривое письмо сотрёт всю историю отсутствий.
Инвариант покрыт integration-тестом `test_failed_file_does_not_wipe_db`.

### Worker (`worker/tasks/erp_absences_sync.py`)

Клон `erp_sync.py`: `run_erp_absences_sync` (cron `minute={5,20,35,50}` — сдвинут
на 5 мин от дней рождения, чтобы не коллидить в lock'ах общего ящика),
`erp_absences_watchdog` (09:05, по `absences_expected_interval_days × 1.5`),
`probe_erp_absences` (зарегистрирован в `integration_health` как
`erp_absences`). Гейтинг: общий `modules.erp_sync.enabled` + per-потоковый
`absences_poll_enabled`.

### API (`api/erp_sync/`)

- `GET/PUT /erp-sync/settings` — общие, с per-потоковыми полями отсутствий.
- `GET /erp-sync/absences/runs`, `GET /erp-sync/absences/runs/{id}` — история.
- `POST /erp-sync/absences/run` (mailbox-trigger), `POST /erp-sync/absences/import-file`
  (multipart-upload для диагностики/первичной настройки).

### Настройка (admin)

Во вкладке «Администрирование → ERP-синхронизация» блок «Фильтры писем»
переименован в **«Дни рождения»**, ниже добавлен блок **«Отсутствия в офисе»**:
`absences_poll_enabled`, `absences_expected_interval_days`, 3 фильтра писем.
Общие поля (enabled/poll_interval/notify_emails/delete_after_fetch) — наверху.
