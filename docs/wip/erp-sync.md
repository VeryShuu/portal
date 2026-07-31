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
- **2026-07-31 (PR2 scope)**: **почтовый контур** — раздел «Email» портала это
  **только исходящий SMTP** (нет там IMAP, факт-чек подтверждает helpdesk-паттерн:
  каждый inbound-модуль держит свой ящик). Поэтому:
  - **Приём (IMAP)** — настройки живут в `erp_sync_settings` (своя singleton,
    уже в PR1): `imap_*` + пароль Fernet. Дополнительно поля фильтрации (см. ниже).
  - **Отправка отчётов** — через общий SMTP-контур портала (`email-settings.json`),
    переиспользуем `enqueue_outbox_email(KIND_GENERIC)`.
- **2026-07-31 (PR2 scope)**: **ящик общий** (вариант B — обоснование: требование
  «почта та, что в разделе Email» указывает на общий контур, а не выделенный
  ящик). Значит фильтрация писем **обязательна**, иначе импорт сломается на
  чужом письме. Поллинг берёт `SEARCH UNSEEN`, фильтрует post-fetch на стороне
  портала (IMAP `SEARCH SUBJECT` ненадёжен с MIME/B-encoded), письма мимо
  фильтра **НЕ** помечаются `\Seen` (не трогаем чужую почту на общем ящике).
- **2026-07-31 (PR2 scope)**: **три поля фильтрации** (все опциональны, но
  рекомендуется заполнить Subject + From):
  - `mail_subject_filter: str | None` — подстрока в теме (напр. «Сотрудники»)
  - `mail_sender_filter: str | None` — email отправителя ERP-системы
  - `mail_attachment_filter: str | None` — имя/расширение вложения (напр. «.xlsx»
    или «Сотрудники») — защита от письма без отчёта; берётся первое вложение,
    подходящее под фильтр
- **2026-07-31 (PR2 scope)**: **двойной гейтинг поллинга**:
  - `modules.erp_sync.enabled` — мастер-переключатель модуля (уже в PR1)
  - `erp_sync_settings.poll_enabled: bool` (default false, миграция 088) —
    отдельный флаг авто-поллинга по cron. Позволяет выключить авто-забор, оставив
    ручной upload. Cron проверяет оба флага.

## Архитектура (pipeline)

```
ERP (2×/нед email) → общий ящик → [ARQ-cron erp_sync_import / ручной запуск]
   → aioimaplib SEARCH UNSEEN → post-fetch фильтр (subject+sender+attachment)
       ├─ подходит   → обработать, mark \Seen
       └─ мимо фильтра → пропустить, НЕ mark \Seen
   → attachment → /data/erp_sync/<run_id>/<name>
   → parser (txt/csv/xlsx/xls via xlrd, auto-encoding BOM→cp1251) → rows[FIO, date, gender]
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

-- 088: дополнения к erp_sync_settings (additive ALTER TABLE, zero-downtime).
-- Таблица создана миграцией 087 — здесь только добавляем недостающие поля.
ALTER TABLE erp_sync_settings
  ADD COLUMN poll_enabled         BOOL     NOT NULL DEFAULT FALSE,
  ADD COLUMN mail_subject_filter  VARCHAR(255),   -- подстрока темы письма (CI)
  ADD COLUMN mail_sender_filter   VARCHAR(255),   -- email/подстрока From
  ADD COLUMN mail_attachment_filter VARCHAR(255); -- имя/расширение вложения
```

> Поля `enabled` / `imap_*` / `poll_interval_seconds` / `expected_interval_days`
> / `notify_emails` уже созданы миграцией 087. Миграция 088 только добавляет
> `poll_enabled` (двойной гейтинг) и три поля фильтрации почты.

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

### ✅ PR1 (фундамент) — ГОТОВ, в PR #50
- [x] миграция 087 (`users.birth_date`/`gender`, `erp_sync_runs`, `erp_sync_settings` без фильтров)
- [x] модели `ErpSyncRun`, `ErpSyncSettings`; регистрация в `models/__init__`
- [x] `birth_date`/`gender` в `UserPublic`/`UserMe`/`AdminPatchProfileRequest` + `users_admin_service`
- [x] module-gate wiring (7 точек): `modules_config`, `deps`, `modules.py`, `bootstrap`, `PUT /admin/modules/erp_sync`
- [x] `schemas/erp_sync.py` (settings/run/test)
- [x] frontend `StaffCard.vue` + `ProfileInfoCard.vue` + `UserPublic`/`UserMe` TS + i18n ru/en
- [x] unit-тесты (schemas, modules, fixtures); ci_lint чист; реген артефактов; доки

### PR2 (pipeline импорта + cron + admin API + уведомления)
- [ ] **миграция 088** (additive `ALTER TABLE erp_sync_settings`): `poll_enabled`, `mail_subject_filter`, `mail_sender_filter`, `mail_attachment_filter`
- [ ] модели: добавить поля в `ErpSyncSettings` (миграция 088)
- [ ] **`xlrd==2.0.1`** в `backend/pyproject.toml` `[project.dependencies]`
- [ ] `app/services/erp_sync/mailbox.py` — IMAP-poll (`aioimaplib`, reuse `secret_crypto`): `SEARCH UNSEEN`, **post-fetch фильтр** (subject+sender+attachment, CI-подстрока), письма мимо фильтра → пропуск **БЕЗ** `\Seen`
- [ ] `app/services/erp_sync/parser.py` — мульти-формат (txt/csv/xlsx/xls via `xlrd`) + авто-кодировка (BOM→cp1251) + дедуп дублей + детект конфликтов
- [ ] `app/services/erp_sync/matcher.py` — оркестрация `users_repo.find_by_full_name_*`, triage 1/0/>1
- [ ] `app/services/erp_sync/importer.py` — основная транзакция: parse→match→update→diff→report; общий `run_import(Attachment)` для mailbox и upload
- [ ] `app/services/erp_sync/report.py` — HTML-отчёт для email (разделы changed/unmatched/ambiguous/conflicts/errors)
- [ ] `app/worker/tasks/erp_sync.py` (`run_erp_sync` cron, проверка `poll_enabled` + `module.enabled` + distributed-lock + interval-guard) + `erp_sync_watchdog.py` (раз в день)
- [ ] `app/worker/tasks/integration_health.py`: probe `erp_sync` (reuse `portal_integration_up{integration="erp_sync"}`)
- [ ] `app/worker/main.py`: cron-регистрация (`run_erp_sync` каждые 15 мин, `erp_sync_watchdog` раз в день)
- [ ] `app/api/erp_sync/settings.py` — `GET/PUT /erp-sync/settings` (write-only password, поля фильтров) + `POST /erp-sync/test` (IMAP-логин + фильтр)
- [ ] `app/api/erp_sync/runs.py` — `GET /erp-sync/runs` (пагинация + report), `GET /erp-sync/runs/{id}`
- [ ] `app/api/erp_sync/run.py` — `POST /erp-sync/run` (mailbox-trigger, `triggered_by=manual`) + **`POST /erp-sync/import-file`** (multipart-upload → общий `run_import`)
- [ ] регистрация роутеров в `app/api/__init__.py` + `ErpSyncModuleEnabled` gate
- [ ] `schemas/erp_sync.py`: поля фильтров в `ErpSyncSettingsIn`/`Out`
- [ ] unit `parser` (5 форматов × кодировки, дедуп, конфликты, скобки, ё/е, невалид)
- [ ] unit `matcher` (exact/words/ambiguous/unmatched)
- [ ] unit `report` (diff, XSS-escape)
- [ ] unit `mailbox`-фильтр (subject/sender/attachment, MIME-encoding edge cases)
- [ ] integration (DSN/testcontainers): полный цикл (insert users → import → assert updates + diff); upload endpoint; mailbox-trigger; watchdog stale → alert; дедуп по Message-ID; письмо мимо фильтра не обрабатывается

### PR3 (frontend admin-вкладка)
- [ ] `api/erp-sync.ts` + `queries/erp-sync.ts` + `queries/keys.ts`
- [ ] `pages/admin/tabs/ErpSyncTab.vue` (форма настроек: IMAP + poll_enabled + poll_interval + expected_interval + notify_emails + **3 поля фильтров** + кнопки «Запустить»/«Загрузить файл»/«Проверить подключение»)
- [ ] история runs (таблица + expandable report)
- [ ] регистрация вкладки в `AdminPage.vue` (группа `system`)
- [ ] i18n `admin.erpSync.*` ru/en

### Финал (по PR2/PR3)
- [ ] ci_lint (ruff+mypy) + pytest unit
- [ ] реген `openapi.json` / `types_gen` / `tests.generated.md`
- [ ] docs `docs/erp-sync.md` (модульный док) + `docs/README.md` + `docs/db-schema.md` (миграция 088) + `docs/api-contracts.md` + `docs/monitoring.md`
- [ ] PR → 16 checks green → merge

## Грабли / контекст

- **Раздел «Email» = только SMTP** (факт-чек 2026-07-31). Там нет IMAP. Входящая
  почта (IMAP) — per-feature singleton (как `helpdesk_mailbox_settings`). Не
  пытаться «переиспользовать IMAP из раздела Email» — его там нет. Настройки
  приёма ERP живут в `erp_sync_settings`; отправка отчётов — через общий SMTP.
- **Общий ящик = обязательная фильтрация.** Если на ящик сыплется разная почта,
  без фильтра по теме/отправителю импорт сломается на чужом письме (или
  пометит его `\Seen`, испортив чужой inbox). Поллинг обязан: (1) фильтровать
  post-fetch (IMAP `SEARCH SUBJECT` ненадёжен с MIME/B-encoded кириллицей),
  (2) письма мимо фильтра **НЕ** помечать `\Seen`. Три поля:
  `mail_subject_filter`, `mail_sender_filter`, `mail_attachment_filter`.
- **Двойной гейтинг поллинга**: `modules.erp_sync.enabled` (вся фича) AND
  `erp_sync_settings.poll_enabled` (только авто-забор). Без второго нельзя
  выключить поллинг, оставив ручной upload. Cron проверяет оба.
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
