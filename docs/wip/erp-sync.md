# Фича: ERP-синхронизация дней рождения и пола сотрудников

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Создаётся, как только ясно, что задача не закроется за одну сессию; удаляется
> после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Автоматический импорт даты рождения и пола сотрудников из ERP-выгрузки
(email → вложение) с FIO-матчингом против `users.full_name`, записью в
`users.birth_date` / `gender` и много-канальным уведомлением админа о результате.
Данные видны всем авторизованным в карточке сотрудника (как телефоны).
Источник истины — ERP: каждый импорт перетирает значения.

## Контекст / источник данных

ERP (1С) шлёт письмо на служебный ящик 2 раза в неделю. Во вложении — отчёт
«Справочник: Сотрудники» с колонками: **ФИО**, **дата рождения** (`ДД.ММ.ГГГГ`),
**пол** (`Мужской`/`Женский`). Формат на выбор (5 вариантов было приложено):
`.xls` (OLE2), `.xlsx`, `.txt` (UTF-8 / cp1251), `.csv`, HTML-таблица.

**Договориться с ERP на `TXT` (UTF-8, tab-separated)** — минимальные зависимости,
но парсер делать устойчиво к любому из форматов + авто-детект кодировки, чтобы
«пересохранение в Excel» ничего не сломало молча.

## Решения по ходу

- **2026-07-31**: архитектура — **email → IMAP-poll по cron → парсер → FIO-матч → UPDATE users**.
  Переиспользует существующий паттерн helpdesk-ингресса (`aioimaplib` +
  distributed-lock + interval-guard + Fernet-singleton-настроек). НЕ вебхук
  (intranet-SMTP скорее всего не поддерживает push), НЕ ручной запуск (теряем
  автоматизацию). Poll ~каждые 15 мин, дедуп по `Message-ID`.
- **2026-07-31**: перетирание ручных правок — **ERP всегда перетирает**
  (без `*_source`-колонок). Осознанный выбор заказчика. Компенсация: в отчёт
  админу после каждого импорта выводим **diff** (что изменилось с прошлого раза),
  чтобы админ видел перетирание и мог реагировать через ERP.
- **2026-07-31**: видимость даты/пола — **все авторизованные, полностью**
  (с годом), как телефоны. `birth_date`/`gender` в `UserPublic`/`UserMe`.
- **2026-07-31**: уведомления админу — **email (email_outbox) + in-app
  (колокольчик) + Grafana/health-probe** (все три канала). Отдельный watchdog-cron
  на случай «письма нет >N дней».
- **2026-07-31**: триггер — **poll ящика по cron** (как helpdesk).
- **2026-07-31**: **кнопка принудительной синхронизации** в админке
  (`POST /erp-sync/run`) — запускает тот же pipeline синхронно, возвращает
  сводку результата (matched/unmatched/ambiguous/errors + report). Для
  отладки/реверификации без ожидания cron.
- **2026-07-31**: **полный email-отчёт админу** после каждого импорта (и
  автоматического, и ручного): HTML-таблица с разделами «Обновлено» (со
  списком изменённых полей, новое↔старое значение), «Не сопоставлено» (ФИО из
  ERP, которого нет на портале), «Неоднозначно» (ФИО → N кандидатов),
  «Конфликты в файле» (одно ФИО с разными датами/полом), «Ошибки парсинга».
- **2026-07-31**: **обработка дублей в ERP** (несколько строк одного
  сотрудника из-за нескольких должностей):
  - **ФИО + дата + пол полностью совпадают** → дедуплицируем (берём любую,
    данные идентичны), пишем 1 раз. Это норма.
  - **ФИО совпадает, но дата рождения ИЛИ пол различаются** → возможный
    однофамильца в ERP (или ошибка выгрузки). **Не пишем ничего**, выводим как
    ошибку в раздел отчёта «Конфликты в файле» для ручного разбора админом.
  - Решение принято заказчиком; логика живёт в `parser` (дедуп) и
    `importer`/`report` (конфликты).
- **2026-07-31 (PR2 scope)**: **форматы файлов — поддержать ВСЕ 5** из
  приложенных заказчиком (`txt`/`csv`/`xlsx`/`xls` + авто-кодировка BOM→cp1251).
  `.xls` (legacy OLE2) парсится через `xlrd==2.0.1` (лёгкий dep ~200 КБ,
  формат заморожен; добавляется в `pyproject.toml`); `xlsx` — через `openpyxl`
  (уже в deps); `txt`/`csv` — `csv`-модуль. Ранее рекомендовал отклонять `.xls`
  — **решение пересмотрено**: `.xls` физически присутствовал в реальных
  выгрузках, риск потери цикла при пересохранении оператором перевешивает цену dep.
- **2026-07-31 (PR2 scope)**: **ручной запуск — две кнопки в admin UI**:
  1. **«Запустить синхронизацию»** (основная) — mailbox-trigger: форсирует
     немедленный IMAP-poll (`run_erp_sync` cron-pipeline с
     `triggered_by=manual`). Покрывает 95% случаев («письмо пришло → нажал →
     получил отчёт сейчас, не ждать 15 мин»).
  2. **«Загрузить файл вручную»** (второстепенная, для диагностики/первичной
     настройки/миграции) — multipart-upload через `POST /erp-sync/import-file`,
     вызывает тот же `importer.run_import()` (источник файла — тело запроса, не
     IMAP). Работает даже при ненастроенном/недоступном ящике; идеальна для
     первичной верификации парсера на реальном файле и разбора проблемных
     выгрузок. В UI можно спрятать за «Расширенные».
  Общий `importer.run_import()` абстрагирован от источника (принимает
  `Attachment`-объект `{name, bytes, hash}`); mailbox и upload различаются
  только наполнением этого объекта.

## Архитектура (pipeline)

```
ERP (2×/нед email) → mailbox → [ARQ-cron erp_sync_import / ручной запуск]
   → aioimaplib SEARCH UNSEEN → attachment → /data/erp_sync/<run_id>/<name>
   → parser (txt/csv/xls/xlsx, auto-encoding) → rows[FIO, date, gender]
   → dedup по нормализованному ФИО:
       ├─ одинаковые во всех полях  → 1 запись (норма)
       └─ разные дата/пол при том же ФИО → конфликт[] (НЕ пишем)
   → per-row matcher (reuse users_repo.find_by_full_name_exact → words):
       ├─ 1 match  → UPDATE birth_date+gender (всегда) + diff в report.changed
       ├─ 0 match  → unmatched[]
       └─ >1 match → ambiguous[] (НЕ пишем)
   → commit (в той же транзакции: email_outbox + notification)
   → health-probe: erp_sync=1, last_success_at=now, prometheus gauge
   → IMAP \Seen
[watchdog cron /day]: if now - last_success_at > expected_interval_days × 1.5 → alert
```

## Схема БД (миграция 087 + 088, additive, zero-downtime)

```sql
-- 087: поля сотрудника + лог импортов
ALTER TABLE users
  ADD COLUMN birth_date DATE NULL,
  ADD COLUMN gender VARCHAR(10) NULL;          -- CHECK ('male','female')

CREATE TABLE erp_sync_runs (
  id BIGSERIAL PRIMARY KEY,
  message_id TEXT UNIQUE,                       -- дедуп писем (NULL для ручного запуска)
  attachment_hash TEXT,
  attachment_name TEXT,
  triggered_by VARCHAR(20) NOT NULL,            -- 'cron' | 'manual'
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at  TIMESTAMPTZ,
  status       VARCHAR(20) NOT NULL,            -- success|partial|failed|skipped
  rows_total     INT,
  rows_matched   INT,
  rows_updated   INT,
  rows_unmatched INT,
  rows_ambiguous INT,
  conflicts      INT,
  errors         INT,
  report JSONB NOT NULL DEFAULT '{}'            -- {changed:[{user_id,fio,field,old,new}],
                                                --  unmatched:[{fio,date,gender}],
                                                --  ambiguous:[{fio,candidates:[...]}],
                                                --  conflicts:[{fio,variants:[{date,gender}]}],
                                                --  errors:[{raw,reason}]}
);

-- 088: настройки ящика (singleton, клон HelpdeskMailboxSettings)
CREATE TABLE erp_sync_settings (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  enabled BOOL NOT NULL DEFAULT false,
  imap_host VARCHAR(255), imap_port INT DEFAULT 993, imap_use_ssl BOOL DEFAULT true,
  imap_username VARCHAR(255), imap_password_enc TEXT,         -- Fernet, write-only
  imap_folder VARCHAR(100) DEFAULT 'INBOX',
  poll_interval_seconds INT NOT NULL DEFAULT 900 CHECK (poll_interval_seconds BETWEEN 60 AND 3600),
  expected_interval_days INT NOT NULL DEFAULT 4,
  notify_emails TEXT[]                                          -- NULL = всем admin с notify_email=true
);
INSERT INTO erp_sync_settings (id) VALUES (1);
```

## Статус по PR

- **PR1 (фундамент) — ГОТОВ, PR #50 открыт** (`feat/erp-sync-foundation`):
  миграция 087, модели ErpSyncRun/Settings, birth_date/gender в схемах +
  admin_patch + module-gate (7 точек), frontend (StaffCard/ProfileInfoCard +
  i18n), unit-тесты, ci_lint чист. Ожидает мёрджа после 16 CI checks.
- **PR2 (pipeline импорта) — следующий**. Scope зафиксирован выше (форматы:
  все 5; ручной запуск: mailbox-trigger + multipart-upload). Отправная точка —
  модели/схемы/module-gate из PR1 уже на месте; нужно реализовать
  `services/erp_sync/*`, worker-tasks, `api/erp_sync/*`, тесты, модульный док.
- **PR3 (frontend admin-вкладка) — после PR2**. Зависит от API PR2.

## Чеклист (DoD)

### Backend
- [ ] миграция 087 (`birth_date`, `gender` на `users`; таблица `erp_sync_runs`)
- [ ] миграция 088 (singleton `erp_sync_settings`)
- [ ] модели `app/models/erp_sync.py` (`ErpSyncRun`, `ErpSyncSettings`)
- [ ] `birth_date`/`gender` в `UserPublic` + `UserMe` (Pydantic `app/schemas/user.py`)
- [ ] admin-edit `birth_date`/`gender` в `AdminPatchProfileRequest` + `users_admin_service`
- [ ] `app/services/erp_sync/mailbox.py` — IMAP-poll (копия helpdesk-ingress, reuse `secret_crypto`)
- [ ] `app/services/erp_sync/parser.py` — мульти-формат (txt/csv/xlsx/**xls** через `xlrd==2.0.1`) + авто-кодировка (BOM→cp1251) + дедуп дублей + детект конфликтов
- [ ] `xlrd==2.0.1` добавлен в `backend/pyproject.toml` (`[project.dependencies]`)
- [ ] `app/services/erp_sync/matcher.py` — оркестрация `users_repo.find_by_full_name_*`, triage 1/0/>1
- [ ] `app/services/erp_sync/importer.py` — основная транзакция: parse→match→update→diff→report
- [ ] `app/services/erp_sync/report.py` — HTML-отчёт для email (разделы changed/unmatched/ambiguous/conflicts/errors)
- [ ] `app/worker/tasks/erp_sync.py` (`erp_sync_import` cron) + `erp_sync_watchdog.py`
- [ ] `app/api/erp_sync/` — CRUD настроек + `GET /runs` + `POST /run` (mailbox-trigger, manual) + `POST /import-file` (multipart-upload, общий `run_import`) + `POST /test`
- [ ] module-gate `modules.json: erp_sync.enabled`; регистрация в `app/api/__init__.py` + `app/worker/main.py::cron_jobs`
- [ ] health-probe в `integration_health` + Prometheus gauge (`erp_sync:last_success_at`)

### Frontend
- [ ] `StaffCard.vue`: явные слоты для `birth_date` (formatDate) и `gender` (текст/иконка) — НЕ через attribute-schema
- [ ] TS-тип `UserPublic` в `api/users.ts` + реген `types.gen.d.ts`
- [ ] Admin: вкладка/секция «ERP-синхронизация» (настройки ящика + список runs с отчётами + **кнопка «Запустить синхронизацию»** + «Проверить подключение»)
- [ ] i18n ключи в `ru.json` + `en.json` синхронно (`erp_sync.*`, `staff.birth_date`, `staff.gender`)

### Тесты
- [ ] unit `parser` (5 форматов × кодировки, дедуп дублей, конфликты, скобки `(...)` в ФИО, ё/е, невалидные даты/пол)
- [ ] unit `matcher` (exact/words/ambiguous/unmatched; edge-кейсы из `test_meetings_participants.py`)
- [ ] unit `report` (diff, форматирование)
- [ ] integration (DSN/testcontainers): полный цикл insert users → import → assert updates + diff; ручной запуск через API; watchdog stale → alert; дедуп по Message-ID

### Финал
- [ ] ci_lint (ruff+mypy в CI-окружении) + pytest unit
- [ ] реген `openapi.json` / `types_gen` / `tests.generated.md`
- [ ] docs `docs/erp-sync.md` (модульный док по шаблону) + правка `docs/README.md` + `docs/db-schema.md` + `docs/api-contracts.md` + `docs/roles-matrix.md`
- [ ] PR → 16 checks green → merge

## Грабли / контекст

- **`users.full_name` — одна свободная строка** (приходит из Keycloak, порядок слов
  не гарантируется: «Last First Patronymic» либо иначе). Не полагаться на
  парсинг по словам; использовать `find_by_full_name_words` (матчит в любом порядке).
- **ФИО с примечаниями в скобках** (`Зубайрова ... (Сухорукова с 01.09.2021)`) —
  обрезать по `(` перед матчингом. Скобки ломают точный матч.
- **Кодировка вложения — ловушка.** Один из приложенных файлов был cp1251. Парсер
  обязан детектить (BOM → chardet → cp1251 fallback), не хардкодить utf-8.
- **`find_by_full_name_words` использует `ilike` — на 300 строк это ОК**, но
  каждая строка = отдельный round-trip в БД. Если тормозит — батчить или
  кешировать список пользователей на время импорта (300 строк × ~2 запроса = 600
  запросов, приемлемо).
- **Soft-deleted (`deleted_at IS NOT NULL`) пользователи исключаются** матчем
  автоматически (условие в `users_repo`). Дубликаты среди удалённых не страшны.
- **Russian TLS (Минцифры)**: если ERP-ящик на `.ru`-хосте — `aioimaplib`
  использует системный trust store (`ssl.create_default_context`), сертификат
  `russian_trusted_root_ca.crt` уже в образе (`backend/Dockerfile`).
- **`full_name` может прийти из Keycloak-атрибута** (флаг `is_full_name_source` в
  `user_attribute_mappings`). На матчинг это не влияет (матчим по текущему
  значению колонки), но обновлять `birth_date`/`gender` мы можем независимо — это
  наши нативные колонки, не KC-атрибуты.
- **Email-отчёт должен быть читаемым**, а не спамом. Toggle «прислать отчёт
  только если есть warnings» (default on) — успех без изменений = тишина.
- **Дедуп по `Message-ID`**: если письмо уже обработано — пропуск без ошибки
  (helpdesk так же). Защищает от повторной обработки при перезапуске воркера.
- **Дедуп строк в файле**: ERP выгружает одного человека N раз (несколько
  должностей). Норма — данные идентичны, берём 1. Конфликт — данные разные при
  том же ФИО, НЕ пишем, в отчёт «Конфликты в файле».
- **Per-row rollback**: при ошибке одной строки `db.rollback()` бы откатил всю
  транзакцию. Поэтому сбор данных идёт в памяти (списки changed/unmatched/...),
  а UPDATE-цикл + commit — в конце одним батчем. См. helpdesk-паттерн
  (`ingress._process_uid` ловит исключения, rollback'ит сессию, продолжает).
