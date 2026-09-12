# Directum: просроченные задачи → уведомления в Matrix

> Модуль интеграции с СЭД Directum. Архитектурно — клон паттерна
> [`erp-sync.md`](./erp-sync.md) (singleton-настройки + колонки-группы per-задача +
> runs-лог + ARQ cron с расписанием по часам), но источник данных — HTTP OData вместо
> IMAP. Миграция **098**. Зафиксированные продуктовые решения — §2, история
> разработки — в git-истории (`feat/directum-sync`, `fix/directum-manual-run-ux`).

## 1. Что делает

Первая (и пока единственная) задача — **«Просроченные задачи»**: по расписанию
портал запрашивает у Directum список заданий в работе с истёкшим сроком,
находит исполнителей среди сотрудников портала (по ФИО) и отправляет каждому
**дайджест** в личный чат Matrix (одним сообщением, не по сообщению на задачу).

```
cron (ежечасно :17, расписание по часам MSK) ──► OData GET IAssignments
        $filter=Deadline lt NOW and Status eq 'InProcess'
        $select=Id,Subject,Deadline
        $expand=Performer($select=Name)
        $top=100&$skip=… (пагинация, ≤50 страниц)
                │
                ▼
  группировка по Performer.Name ──► ФИО-матчинг (users_repo:
  exact → by-words; ё→е, падежи, раскладка)
                │
     ┌──────────┼─────────────┬──────────────────┐
     ▼          ▼             ▼                  ▼
  Matched    Matched        Ambiguous         Unmatched
  +opt-in    без opt-in     (однофамильцы)    (нет на портале)
     │          │                │                  │
     ▼          ▼                ▼                  ▼
  matrix    skipped_opt_in   в отчёт           в отчёт
  outbox    (в отчёт)
     │
     ▼
  messenger_outbox (provider='matrix', chat_id=MXID)
  → воркер доставки: DM-резолв → отправка (идемпотентно по txnId)
```

После прогона — **email-сводка** админам (`notify_emails` или все админы с
`notify_email=true`): счётчики + список уведомлённых + пропущенных из-за
выключенного opt-in + ненайденных/неоднозначных ФИО. Прогон с 0 задач письмо
не шлёт.

## 2. Зафиксированные решения (2026-08-17)

| Решение | Значение |
|---|---|
| Учётка OData | Сервисная AD-учётка (например `PDC1\portal-directum`), права на чтение `IAssignments`. Логин+пароль в `directum_settings`, пароль Fernet (`auth_password_enc`), write-only в API |
| TLS | Сертификат `sed.mage.ru` валиден; httpx с системным trust store (`ssl.create_default_context()`) |
| Matrix opt-in | **Соблюдаем** `users.preferences.chat_notifications_enabled` (дефолт выкл.): получают только включившие; пропущенные — в сводке прогона. Включение: профиль сотрудника → уведомления, или `PATCH /users/admin/{id}/notification-preferences` |
| Повторы | Уведомляем **каждый прогон** (dedup-таблицы нет) — интервал задаёт частоту напоминаний. Ручной «Запустить сейчас» тоже рассылает |
| Расписание | У каждой задачи свои **часы запуска** (только часы, московское время +03:00 — как у Directum): например 10, 12, 14 = прогоны в 10:17, 12:17, 14:17. Cron тикает ежечасно в :17, воркер сверяет текущий час MSK с `overdue_run_hours`; дедуп — один прогон в час (Redis-ключ). Пусто = авто-прогонов нет (решение 2026-08-17, миграция 099) |
| Формат | Дайджест на сотрудника: «🔴 Просроченные задачи в Directum — N» + нумерованный список (тема, срок, «просрочено на X дн.»), кап 50 задач в сообщении |
| OData-запрос | Зашит в код per-задача (`overdue_*` — колонка-группа настроек, как `absences_*` в erp_sync). В `$select` добавлен `Id` — стабильная идентификация в отчётах |
| «Удалять письмо» | Не переносится из erp_sync (писем нет); смысловой аналог «не обрабатывать повторно» покрыт решением про повторы |

## 3. Схема БД (миграция 098)

| Таблица | Назначение |
|---|---|
| `directum_settings` | Singleton (`id=1`, `CHECK (id=1)`), сеется миграцией. Общие: `enabled`, `base_url` (default `https://sed.mage.ru/Integration/odata`), `auth_username`, `auth_password_enc` (Fernet), `expected_interval_days` (watchdog, default 2), `notify_emails` (NULL = все админы). Задача 1: `overdue_enabled` + `overdue_run_hours INTEGER[]` (часы 0–23, CHECK-подмножество; пусто = авто-прогонов нет) |
| `directum_runs` | Лог прогонов: `triggered_by('cron'/'manual')`, `status('success'/'partial'/'failed'/'skipped')`, счётчики (`tasks_total`, `performers_total`, `users_notified`, `users_skipped_opt_in`, `users_unmatched`, `users_ambiguous`, `errors`), `report` JSONB, index `started_at DESC` |

`report` JSONB: `notified` / `skipped_opt_in` / `unmatched` (`[{fio, tasks}]`),
`ambiguous` (`[{fio, tasks, candidates}]`), `matrix_disabled`, `error` (для
failed), `truncated` (кап 200 элементов на список).

Статусы: `success` — выборка получена (unmatched/ambiguous — данные, не сбой);
`partial` — Matrix-бот не настроен при наличии получателей или ошибки
исполнителей; `failed` — OData-запрос не выполнен (креды/сеть).

## 4. Гейтинг (тройной)

1. `modules.directum.enabled` (modules.json, мастер-переключатель) — вкладка
   «Модули» админки; при выкл. весь `/api/v1/directum/*` → 404, cron-задача
   скипается, вкладка скрыта (`TAB_MODULE_GATE`).
2. `directum_settings.enabled` («Модуль включён» во вкладке) — гейтит и cron,
   и ручной запуск. `enabled=true` требует полных кредов (PUT → 400).
3. `directum_settings.overdue_enabled` («Просроченные задачи») — только
   авто-прогон; ручной «Запустить сейчас» обходит (как `poll_enabled` в erp).

Skip-причины run-строку **не создают** (иначе ежечасный cron-тик заспамил бы
историю): `module_disabled` / `disabled` / `overdue_disabled` /
`not_scheduled_hour` / `already_ran_this_hour` / `not_configured` / `lock_held` — только логи.

## 5. Backend

- **Сервисы** `app/services/directum/`:
  - `odata.py` — singleton httpx-клиент (`Timeout(15, connect=5)`, системный
    trust store, `instrument_httpx_client(target='directum')`), basic auth,
    пагинация; `DirectumApiError`/`DirectumTransportError` + `classify_error`
    (transient/permanent). `ping()` — пробный `$top=1` для кнопки «Проверить
    подключение».
  - `matcher.py` — клон erp-матчера: `find_by_full_name_exact` →
    `find_by_full_name_words`, триаж `Matched/Ambiguous/Unmatched`.
  - `digest.py` — plain+HTML дайджест (экранирование тем, кап 50).
  - `sync.py` — оркестрация `run_directum_sync(db, *, triggered_by)`: fetch →
    группировка → матчинг → `enqueue_messenger_message` (matrix, MXID из email
    через `matrix_id_for_user`) + run-строка + email-сводка — **один commit**
    (outbox-инвариант). Matrix-бот не настроен → без уведомлений, статус
    `partial`, причина в отчёте.
  - `report.py` / `recipients.py` — email-сводка и адресаты (клоны erp).
- **API** `app/api/directum/` (все admin-only + `require_directum_module`):
  `GET/PUT /directum/settings`, `POST /directum/test`, `POST /directum/run`
  (ARQ `run_directum_sync`, `_job_id` уникален на каждое нажатие — uuid-суффикс;
  при `enabled=false` отвечает 400 сразу, без тихого скипа), `GET /directum/runs[/{id}]`.
- **Воркер** `app/worker/tasks/directum_sync.py`: cron ежечасно `minute=17`;
  расписание — «текущий московский час ∈ `overdue_run_hours`» + дедуп часа
  (`directum:last_run_hour`, Redis, TTL 48ч); lock `directum:poll_lock`
  (SET NX EX + Lua); `directum_watchdog` (09:10 daily, алерт если
  `expected_interval_days × 1.5` без успеха); `probe_directum` — строка
  `directum` в панели здоровья интеграций. Минута запуска всегда :17
  (минута cron-тика не зависит от сдвига целых часов).

## 6. Frontend

- Вкладка `?tab=directum` в группе `system` (после ERP-синхронизации):
  `DirectumTab.vue` = `DirectumSettings` + действия («Запустить сейчас» с
  поллингом истории 3с/90с; если прогон не появился за 90с — баннер-предупреждение
  вместо вечной «зелёной очереди») + `DirectumRuns` (таблица с раскрытием отчёта).
- `DirectumSettings.vue` — «Общие настройки» (enabled, base_url, логин,
  пароль-write-only с плейсхолдером «задан», периодичность, получатели) →
  разделитель → «Просроченные задачи» (overdue_enabled + **часы запуска** —
  мультиселект 00:00–23:00 московского времени + hint про opt-in; включение
  задачи без часов блокируется). Кнопка «Проверить подключение» (заблокирована
  при несохранённых правках — тестирует сохранённые креды).
- Карточка мастера в «Модулях» (`useModulesState`: `onToggleDirectum`,
  `goToDirectum`), `ModuleName 'directum'` в stores/modules.

## 7. Настройка (админ)

1. «Модули» → карточка **Directum** → включить.
2. Вкладка **Directum**: указать base_url (дефолт подходит), логин/пароль
   сервисной AD-учётки → «Сохранить» → «Проверить подключение».
3. Включить «Модуль включён» и «Просроченные задачи», выбрать часы запуска
   (московское время; например 10, 12, 14).
4. Убедиться, что Matrix-бот настроен (админка → «Корпоративный чат») — без
   него прогоны будут `partial`.
5. (Постепенно) включать `chat_notifications_enabled` сотрудникам — до
   включения они попадают в сводку как `skipped_opt_in`.

Нюанс переключателей: «Просроченные задачи» гейтит только **авто-прогоны по
расписанию**; кнопка «Запустить сейчас» работает и при выключенном переключателе
(но требует «Модуль включён» — иначе мгновенная ошибка 400). «Модуль включён»
нельзя включить без заполненных кредов, а задачу — без хотя бы одного часа
запуска (PUT вернёт 400).

## 8. Эксплуатация

- **Прогоны, которых «не видно»**: skip-причины (`module_disabled`,
  `disabled`, `overdue_disabled`, `not_scheduled_hour`, `already_ran_this_hour`,
  `not_configured`,
  `lock_held`) run-строку **не создают** — они видны только в логах воркера
  (`directum.worker.*` / ответ cron-задачи) и как отсутствие новых строк в
  истории вкладки. Не путать с `failed`-прогоном (OData недоступен/креды) —
  тот создаёт строку и шлёт алерт-письмо.
- **Watchdog** (09:10 ежедневно): если успешных прогонов не было дольше
  `expected_interval_days × 1.5` — email + in-app алерт админам.
- **Health-панель** (интеграции): строка `directum` — свежесть последних
  успешных прогонов.
- **Email-сводка** приходит только на непустые прогоны (есть задачи или
  сбой) — пустого письма «0 задач» нет.
- **Ретеншн историй** (решение 2026-08-17, хардкод): cron 04:40 ежедневно
  удаляет runs-строки старше **7 дней** из `erp_sync_runs`,
  `erp_absences_runs` и `directum_runs` (`app/worker/tasks/runs_cleanup.py`).
  Отправленные письма/сообщения в очередях (`email_outbox`/`messenger_outbox`,
  только SENT) тоже чистятся после **7 дней** (было 30); DLQ/FAILED не
  трогаются — остаются для разбора.

## Gotchas

- Performer.Name бывает нестандартным («Капитан судна Н.Трубятчинский») →
  `Unmatched` → сводка админам; задачи без исполнителя — тоже Unmatched.
- ARQ: `enqueue_job` — короткое имя `run_directum_sync`; cron — FQN.
- **`_job_id` ручного запуска уникален на каждое нажатие** (uuid-суффикс):
  фиксированный id дедуплицировался ARQ по ключу `arq:job:<id>` (~1 час TTL)
  и молча глотал повторные нажатия; от спама защищает `directum:poll_lock`.
  При выключенном `settings.enabled` API отвечает 400 сразу (скип в воркере
  молчал — run-строку скип не создаёт, кнопка крутилась впустую).
- `messenger_outbox.chat_id` для matrix — **MXID** (не room_id); DM-комнату
  создаёт воркер доставки через `DmResolver` (`m.direct`).
- Email-сводка идёт с `kind='directum'` (email_outbox без CHECK на kind);
  идемпотентность matrix-отправок — txnId = UUID outbox-строки.
- Пагинация OData — `$skip` до короткой страницы; потолок 50 страниц
  (5000 задач) с warning-логом.
