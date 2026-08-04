# Фича: ERP-синхронизация отсутствий (отпуска/отгулы/болезни/командировки)

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Удаляется после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Второй поток ERP-синхронизации — автоматический импорт отсутствий сотрудников
из отчёта 1С «Кадровая история сотрудников за период» (email → вложение → IMAP-
poll по cron → парсер → FIO-матч → **full-replace** в БД). Аналогично потоку
дней рождения, но данные — ranged-события (диапазон дат), а не скалярные колонки.

**Приёмка + парсинг + запись + настройки — реализованы в этой задаче.**
Отображение отсутствий (виджет «кого нет на неделе», карточка сотрудника,
интеграция в UI) — **следующая задача**.

## Контекст / источник данных

ERP (1С) шлёт отдельное письмо с отчётом «Кадровая история сотрудников за
период». Параметры отчёта: «Стандартный период: 01.01.2026 - 31.12.2026» —
отчёт самодостаточен (содержит весь год). Структура файла — иерархическая:

```
Кадровая история сотрудников за период
Параметры:  Стандартный период: 01.01.2026 - 31.12.2026
Отбор:      "..."
Сотрудник
Должность | Подразделение | Состояние | Начало | Окончание
<ФИО сотрудника>                    ← строка без дат = текущий сотрудник
<должность>\t<подразделение>\t<Состояние>\t<Начало>\t<Окончание>  ← период
```

Формат дат смешанный: колонка «Начало» — с временем (`27.07.2026 0:00:00`),
«Окончание» — без (`09.08.2026`). Разделитель — tab.

7 типов «Состояний» (маппинг в `absences_parser._KIND_MAP`):
`vacation_main` / `vacation_extra` / `unpaid_leave` / `sick` /
`business_trip` / `day_off_paid` / `day_off_unpaid`.

## Решения по ходу

- **2026-08-04**: архитектура — **клон потока дней рождения**. Тот же общий
  IMAP-ящик (ADR-048), та же инфраструктура mailbox/matcher/report, тот же
  cron-паттерн (distributed-lock + interval-guard + watchdog + probe). Отличия:
  новый парсер (иерархическая структура, не 3 фиксированные колонки), новая
  таблица `erp_absences` (ranged), **full-replace** вместо per-field upsert.
- **2026-08-04**: **подфункция модуля `erp_sync`**, не отдельный модуль. Гейт
  `modules.erp_sync.enabled` покрывает оба потока. Per-потоковые настройки
  (переключатель поллинга + фильтры писем + expected_interval) — в общем
  singleton `erp_sync_settings`.
- **2026-08-04**: **full-replace** контракт. Каждый отчёт самодостаточен (весь
  год). Перед вставкой: `DELETE FROM erp_absences WHERE source='erp_sync'` →
  `INSERT` matched. Старые записи исчезнувших сотрудников стираются автоматически.
- **2026-08-04**: **безопасность failed-файла**. При 0 валидных matched-строк
  (битый файл / пустой / только ошибки) БД **не трогается**. Иначе одно кривое
  письмо сотрёт всю историю отсутствий. Инвариант покрыт integration-тестом
  `test_failed_file_does_not_wipe_db`.
- **2026-08-04**: **только сопоставленные** пользователи (user_id NOT NULL).
  Незнакомые ФИО → `report.unmatched`, в БД не пишутся.
- **2026-08-04**: **все 7 типов** из файла сохраняются (включая болезни и
  командировки — они полезны для виджета «кого нет»).
- **2026-08-04**: **отдельная таблица логов** `erp_absences_runs` (клон
  `erp_sync_runs`) — независимый дедуп по `message_id` и своя история. Контракт
  дней рождения не трогаем.
- **2026-08-04**: **вынос общих хелперов** парсера в `parser_utils.py`
  (`decode_text`/`detect_delimiter`/`extract_text_records`/`extract_xlsx_records`/
  `extract_xls_records`). Рефакторинг `parser.py` — поведение 1:1, проверено
  существующими unit-тестами дней рождения (35/35 зелёные).

## Архитектура (pipeline)

```
ERP (периодически email) → общий ящик → [ARQ-cron run_erp_absences_sync / ручной запуск]
   → mailbox.fetch_unread_attachments (SEARCH ALL, post-fetch фильтр mail_absences_*)
       ├─ подходит   → обработать (дедуп по message_id в erp_absences_runs)
       └─ мимо фильтра → пропустить, НЕ mark \Seen
   → absences_parser (иерархическая структура: ФИО-строка + строки-периоды)
       → rows[fIO, kind, position, department, start_date, end_date]
       → дедуп по (fio_norm, kind, start, end)
   → matcher (reuse find_by_full_name_exact → words):
       ├─ 1 match  → кандидат на INSERT
       ├─ 0 match  → unmatched[] (не пишем)
       └─ >1 match → ambiguous[] (не пишем)
   → при наличии matched-строк:
       DELETE FROM erp_absences WHERE source='erp_sync'
       INSERT matched
   → commit (в той же транзакции: erp_absences_runs + email_outbox + notification)
   → watchdog cron/day: if last_success > absences_expected_interval_days × 1.5 → alert
```

## Схема БД (миграция 092, additive, zero-downtime)

```sql
CREATE TABLE erp_absences (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        VARCHAR(40) NOT NULL,   -- CHECK enum (7 значений)
  position    TEXT,
  department  TEXT,
  start_date  DATE NOT NULL,
  end_date    DATE NOT NULL,          -- CHECK end >= start
  source      VARCHAR(20) NOT NULL DEFAULT 'erp_sync',  -- 'erp_sync' | 'manual'
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_erp_absences_user_id ON erp_absences (user_id);
CREATE INDEX ix_erp_absences_dates ON erp_absences (start_date, end_date);

CREATE TABLE erp_absences_runs (  -- клон erp_sync_runs, rows_inserted вместо rows_updated
  ... message_id TEXT UNIQUE, status, rows_total/matched/inserted/unmatched/ambiguous,
      errors, report JSONB ...
);

ALTER TABLE erp_sync_settings  -- per-потоковые настройки отсутствий
  ADD COLUMN absences_poll_enabled BOOL NOT NULL DEFAULT FALSE,
  ADD COLUMN mail_absences_subject_filter VARCHAR(255),
  ADD COLUMN mail_absences_sender_filter VARCHAR(255),
  ADD COLUMN mail_absences_attachment_filter VARCHAR(255),
  ADD COLUMN absences_expected_interval_days INT NOT NULL DEFAULT 7;
```

## Статус

- **Приёмка + парсинг + запись + настройки — ГОТОВО** (ветка `feat/erp-absences`).
  Миграция 092, модели, парсер, импортёр, отчёт, воркер (cron + watchdog + probe),
  API (4 endpoints), frontend (настройки перегруппированы: «Дни рождения» +
  «Отсутствия в офисе»), unit-тесты (parser 49 + report 14 + schemas), integration-
  тесты (9 сценариев на реальной БД, все зелёные).
- **Отображение отсутствий — следующая задача** (виджет «кого нет на неделе»,
  карточка сотрудника, история запусков отсутствий в admin UI).

## Чеклист (DoD) — приёмка + парсинг

- [x] миграция 092 (`erp_absences`, `erp_absences_runs`, колонки настроек)
- [x] модели `ErpAbsence`, `ErpAbsencesRun`; расширение `ErpSyncSettings`
- [x] `parser_utils.py` (общие хелперы, вынесены из parser.py)
- [x] `absences_parser.py` (иерархическая структура, 7 kinds, mixed-даты)
- [x] `absences_importer.py` (full-replace + безопасность failed-файла)
- [x] `absences_report.py` (HTML/plain, XSS-escape, разделы inserted/unmatched/...)
- [x] `worker/tasks/erp_absences_sync.py` (cron + watchdog + probe)
- [x] регистрация в `worker/main.py` (cron `minute={5,20,35,50}`, watchdog 09:05)
- [x] probe в `integration_health.py`
- [x] API: `absences_runs.py` + `absences_run.py` + расширение `settings.py`
- [x] frontend: `ErpSyncSettings.vue` (перегруппировка) + `api/erpSync.ts` + i18n ru/en
- [x] unit-тесты: parser (49), report (14), schemas (новые поля + ErpAbsencesRunOut)
- [x] integration-тесты: full-replace, disappeared-employee, failed-не-стирает-БД,
      дедуп, unmatched/ambiguous, notifications, поля записей (9 сценариев)
- [x] реген `openapi.json` / `types_gen.d.ts` / `tests.generated.md`
- [ ] обновлены docs/ (erP-sync.md, db-schema, api-contracts) — в процессе
- [ ] ci_lint + pytest unit green → PR → 16 checks → merge

## Чеклист (DoD) — отображение (следующая задача)

- [ ] виджет «кого нет на неделе» (главная / отдел)
- [ ] отсутствия в карточке сотрудника
- [ ] история запусков отсутствий в admin UI (`ErpSyncTab.vue` → `ErpAbsencesRuns`)
- [ ] READ API для отсутствий (`GET /users/{id}/absences`, `GET /absences?from=&to=`)

## Грабли / контекст

- **Смешанный формат дат**: колонка «Начало» — `27.07.2026 0:00:00`, «Окончание» —
  `09.08.2026`. `parse_absence_date` tolerantен к обоим (отрезает ` HH:MM:SS`).
  Регрессионный тест `test_mixed_date_formats_parsed`.
- **Иерархическая структура**: строка без даты = текущий сотрудник; строка с
  датой = период. Признак — `_has_date_in_row` (любая ячейка парсится как дата).
  Период без предшествующего сотрудника → error (не падает).
- **Маппинг «Состояние»→kind**: порядок в `_KIND_MAP` важен. «Отпуск
  неоплачиваемый» ловим раньше «отпуск основной», иначе свалится в vacation_main
  (contains-матчинг). Тест `test_unpaid_leave`.
- **Full-replace инвариант**: DELETE выполняется ТОЛЬКО при наличии matched-строк.
  Проверка — integration-тест `test_failed_file_does_not_wipe_db`. Без этого одно
  битое письмо сотрёт всю историю.
- **Cron сдвинут на 5 мин** (`minute={5,20,35,50}`) относительно дней рождения
  (`{0,15,30,45}`), чтобы два poll'а общего ящика не коллидили в lock'ах.
- **Общие настройки**: `enabled`/`poll_interval_seconds`/`notify_emails`/
  `delete_after_fetch` — общие с днями рождения. Per-потоковые — только
  `absences_poll_enabled` + 3 фильтра + `absences_expected_interval_days`.
- **`absences_poll_enabled` обязателен**: без него пустые absences-фильтры (None)
  пропустят ВСЕ письма ящика в absence-парсер и сломают импорт дней рождения
  (двойной обработкой) или самих отсутствий (чужими письмами).
