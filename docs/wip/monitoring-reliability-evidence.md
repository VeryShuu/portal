# Monitoring reliability: evidence и handoff

> Основание: [ТЗ](./monitoring-reliability-spec.md). Здесь только очищенные результаты; реальные логи и credentials не сохраняются.

## Контекст

- База: `origin/main` = `36cfcfa25ba1aede49917744b32cf17d36acb447` на момент создания ветки.
- Ветка: `codex/monitoring-reliability`, отдельный worktree `/tmp/portal-monitoring-reliability`.
- ТЗ закоммичено как `e5cc1f1b`; ветка соседней CI-задачи не включена.
- Пользователь разрешил разработку 2026-09-07 и продолжение 2026-09-08. Production не менялся.

## MON-01 / AT-01 — verified_test_runtime (backend/worker); CI pending

### Исправление

`backend/app/core/logging.py`: исключения формируются до sanitizers. JSON использует `ExceptionDictTransformer(show_locals=False)`, text — plain exception formatter до ConsoleRenderer. Распознаваемые credentials в URL, headers, assignments маскируются рекурсивно в строках. Произвольный секрет без признаков не распознаётся: payloads нельзя логировать целиком.

31 новый случай в `backend/tests/unit/test_logging_exception_security.py` использует реальный formatter приложения (structlog/stdlib × JSON/text), chains/groups/notes, nested fields, URLs/headers и ограниченный subprocess-тест длинной строки. Тестовая fixture восстанавливает состояние managed/noisy loggers.

### Проверки

| Проверка | Результат | Ограничение |
|---|---|---|
| Исходный набор logging/arq filter/request logging | 94 passed | До исправления, локальный Python 3.12 |
| Новые security-тесты на исходном коде | 26 failed, 4 passed | 30 случаев до добавления отдельной performance-регрессии |
| Итоговый целевой набор | 125 passed, 1 warning | Предупреждение установленного Starlette/httpx, не ошибка теста |
| `backend/scripts/ci_lint.sh` | ruff/format/mypy passed, 926 source files | Существующий venv; зависимости не обновлялись |
| Coverage `app.core.logging` | 90.41% | Целевой набор; не абсолютное покрытие backend |
| `scripts/diff-cover.sh backend` | 25 изменённых строк, 100% | Локальная проверка относительно origin/main |
| Общий unit/security прогон | 5252 passed, 12 skipped (nightly), 1 warning; 323.91 s | Запущен до последней review-правки, окончательная версия проверяется повторно |
| Окончательный unit/security (`-n 4`) | 5253 passed, 12 nightly skips, 4 одинаковых предупреждения Starlette/httpx, 97.71 s | Финальный исходный код; nightly отдельно не запускались |
| Radon изменённого файла | Нет rank D+ | Общий CI quality gate ещё отдельно |
| `scripts/list_tests.sh` | Штатная генерация выполнена | В diff только новые security cases |

### Проверка пути stdout → Alloy → Loki → Grafana

Собственный контейнер `portal-monitoring-security-20260908` с `--network none`, read-only FS, без capabilities; доступ только к исправленному файлу и искусственному emitter. Сервисы пользователя не останавливались/не перенастраивались. Artificial marker — `mon01-acceptance-20260907`, service `portal-monitoring-acceptance`.

В Loki получены 24 записи: ни одного искусственного секрета, в каждой сохранены ValueError и correlation ID. Grafana Explore в Chromium: событие, тип исключения и REDACTED видимы; canary не виден. Изображение не является обязательным доказательством: оно временное, реальные данные из общего Logs-дашборда в репозиторий не копировались.

После review-правки алгоритма маскирования выполнен повтор с marker `mon01-acceptance-20260908-final`: 18 записей в Loki, все без canary и с сохранённым ValueError. Проверка проводилась 2026-09-08 около 06:30 UTC.

Первый технический запуск от 2026-09-07 не достиг pipeline: файл fixture назывался `logging.py` и перекрыл стандартный модуль. Переназван в `portal_logging.py`; этот неуспешный запуск не засчитывается как приёмка.

### Остаточные ограничения

- Исправление находится в ветке; действующие backend/worker ещё не перезапущены с ним.
- Исторические логи и действующие credentials не удалялись/не менялись. [Runbook](../monitoring-log-secret-runbook.md) требует решений владельца.
- Screenshot-service использует отдельный logger: не считать его закрытым этим исправлением.
- Весь этап A и production-инцидент не закрывать одной проверкой backend formatter.

## MON-02 / AT-02 — verified_test_runtime для false-success; классификация причины частична

`track_arq_job` теперь перехватывает `CancelledError`, записывает `cancelled` и повторно поднимает отмену. Это закрывает подтверждённый дефект: внешний deadline ARQ и остановка worker больше не попадают в `succeeded`. Внутренний `TimeoutError` остаётся `timeout`; обычное исключение — `failed`.

Граница доказательства: установленный ARQ применяет `asyncio.wait_for` снаружи декоратора. Декоратор видит один и тот же `CancelledError` для deadline, shutdown и ручной отмены, поэтому не приписывает недоказанную причину. `on_job_end` не получает outcome, а `after_job_end` не решает cron с `keep_result=0`. Retention и retry ради метрики не изменялись. Панель показывает `timeout` и `cancelled` раздельно и прямо описывает смысл данных.

Проверка на выделенном Redis 7 с уникальными queue/job/key и run-scoped cleanup: 34 passed. Реальный `arq.worker.Worker` доказал два сценария: внешний deadline даёт `started + cancelled`, без `succeeded`; ручная отмена сохраняет ARQ retry, а повторная попытка даёт второй `started` и один `succeeded`. Unit-тест также проверяет fail-open учёт при отказе Redis.

AT-02 закрыт в части «не считать timeout/cancel успехом» и сохранения retry. Точное разделение внешнего deadline, shutdown и manual cancel остаётся `open`: для него нужен outcome-источник за пределами task wrapper и отдельное совместимое решение для cron без сохранённого результата.

## MON-03 / MON-04 / MON-16 — verified_test_runtime

HTTP error ratio больше не ограничивает знаменатель значением `1 req/s`: один
запрос в минуту сохраняет математически корректную долю. Отсутствующая серия
5xx при существующем трафике дополняется нулём с labels знаменателя. При
нулевом трафике или отсутствии scrape recording series отсутствует, а Grafana
показывает `No data` и предлагает сверить `Backend scrape`. Техническая HTTP
success ratio переименована и не выдаётся за SLA или полный пользовательский
путь. `PortalHighErrorRate` сохраняет отдельный абсолютный порог ошибок.

Redis keyspace hit ratio вынесен в `portal:redis_keyspace_hit_ratio5m` с той же
семантикой: малый ненулевой поток считается точно, нулевые операции/no scrape
не подменяются нулём. Recording rule используют и дашборд, и alert rule. ARQ
failure-card показывает ноль только при наличии `started`; без ARQ-рядов
остаётся `No data`.

`promtool test rules` в образе Prometheus 3.13.2 проверяет: 100% и 50% HTTP
ошибок при малом трафике, отсутствие 5xx при существующих запросах, 100% Redis
hits при малой частоте, нулевой трафик, отсутствующий scrape, малый абсолютный
объём без alert и устойчивый объём с firing после `for`. Результат локально:
SUCCESS. Тот же файл подключён к обязательному `monitoring / config validation`.

## MON-07 / MON-17 — verified_test_runtime

`probe_integrations` теперь публикует полное поколение `integration:health` в
одном Redis MULTI/EXEC: DEL, актуальный HSET и EXPIRE применяются атомарно. При
отключении одной probe её поле исчезает, пока остальные продолжают обновляться;
при отключении всех hash удаляется. Ошибка EXEC по-прежнему не роняет cron.
Контрпример выполнен на выделенном Redis с уникальным ключом и run-scoped
cleanup: `{keycloak:0,nextcloud:1}` → keycloak disabled → `{nextcloud:1}` → all
disabled → ключ отсутствует.

Synthetic `up` и `duration` теперь имеют независимые seen-set и вычисляют
текущие labels по своим полям. Тесты доказывают удаление обеих серий при
исчезновении flow, отдельное удаление duration при оставшемся up и две NaN
инвалидации в multiprocess-ветке. Целевой набор MON-07/17: 48 passed.

Связанная часть MON-06 для integration probes закрыта следующим разделом:
persistent state теперь различает disabled, stale, down и up. Для synthetic
expected/freshness metadata ещё остаётся открытой.

## MON-06 — частично verified_test_runtime: freshness общего снапшота

Worker теперь ставит `generated_at` и числовой `generated_at_seconds` после
завершения всех сборщиков. API на каждом scrape fail-closed выставляет
`portal_metrics_snapshot_read_success=0` и меняет значение на 1 только после
успешного чтения Redis, разбора JSON-объекта и гидратации. Отдельный
`portal_metrics_snapshot_generated_timestamp_seconds` показывает возраст
последней завершённой публикации.

`PortalMetricsSnapshotStale` с `for: 2m` тревожит при ошибке текущего чтения
или возрасте публикации >120с. 58 целевых unit-тестов прошли; mutation-тест
фиксирует, что timestamp нельзя вернуть к началу сбора. Promtool проверил 55
alert rules и три контрпримера: свежий snapshot молчит, старый и read failure
срабатывают.

Для integration probes добавлен persistent `integration:probe:state`:
`expected`, `last_attempt`, `last_completed`, result и его
`result_expires_at`. Попытка сохраняется до await; полное завершённое поколение
и legacy hash публикуются одним MULTI/EXEC. Истёкший result сохраняет expectation
и timestamps. 84 unit-теста и реальный Redis переход
down/up → disabled one → disabled all прошли; state не имеет TTL. Promtool
проверяет stale, missing result, disabled/fresh, подавление производного
`PortalIntegrationDown` при stale и отображение состояний
`DISABLED=0 / STALE=1 / DOWN=2 / UP=3`.

Граница: отдельный expected/attempt/completed контракт synthetic probe ещё не
реализован. До первого успешного поколения integration expectation отсутствует
(`No data`), а не объявляется disabled. Защита от reverse completion опирается
на уникальность ARQ cron; если появятся параллельные publishers, нужен attempt
generation/CAS.


## MON-06 synthetic — verified_test_static и verified_test_runtime

Источник expected и lifecycle перенесён в screenshot-service, где находятся
`PROBE_ADMIN_EMAIL/PASSWORD`. Новый приватный `/metrics` отдаёт expected,
result_available, last_attempt, last_completed, up и duration; worker только
планирует `/probe`, Redis/backend snapshot больше не дублируют synthetic state.
После restart или 15 минут без завершения прежний зелёный результат исчезает.

Проверки: 44 screenshot-service tests покрывают disabled, оба обязательных
credential, attempt без completion, fresh UP/DOWN, expiry и restart; 92 целевых
backend tests проходят, diff-coverage полного backend diff = 100%. Promtool
валидирует 58 alert rules, 7 recording rules и semantic-сценарии stale, fresh
failure без дубля stale, exporter-down и DISABLED/STALE/DOWN/UP. Образ
`screenshot-service` пересобран без кэша; временный контейнер прошёл `/ready` и
отдал `expected=0`, `result_available=0` без credentials. Prometheus config,
Compose overlay, Grafana JSON/panel IDs и оба изменённых PromQL валидны. Runtime
с настоящими production credentials остаётся `pending_external`.

## MON-10 / MON-11 / AT-10 — verified_local, verified_ci; merged

`track_arq_job` различает исключение (`failed`) и явный неуспешный
структурированный результат (`result_failed`: `ok is False` либо непустой
`error`). Результат возвращается без изменений, ARQ считает job завершённым и
его retry/result policy не меняется. Инвентаризация worker tasks нашла такие
формы у synthetic probe, meetings RSVP, photo import и integration watchdogs.

`PortalArqJobFailures` теперь считает события: минимум три `failed` или
`result_failed` за 10 минут с `for: 1m`. Это обнаруживает постоянно падающий
cron раз в минуту, который старый порог `rate > 0.1/s` не видел. Новый promtool
сценарий проверяет exception/result_failed и отсутствие алерта при двух
событиях. Mutation-контрпример со старой формулой завершился ожидаемым failure:
для обоих минутных cron `got: []`.

Локально: 40 целевых unit tests; расширенный ARQ/registry/hydration/synthetic
набор — 82 passed; отдельный real-ARQ/Redis тест — 1 passed на временном Redis
с динамическим localhost-портом и run-scoped cleanup; полный semantic promtool
набор — SUCCESS. Ruff/format/mypy для 927 файлов прошли; 58 alert rules и
7 recording rules валидны; изменённый dashboard PromQL разобран promtool;
четыре drift-проверки синхронны; backend diff-coverage — 100% (9 строк).
Forgejo PR #239 смёржен как `2ec5f864`: CI run #1609 — 20 success / 9 ожидаемых skips; security run #1610 — 2 success / 3 ожидаемых skips.


## MON-05 / AT-15 — verified_local, verified_ci, pending_external

`login_and_load` больше не принимает сам факт монтирования `#app` за рабочий
портал. После local login браузер требует marker
`data-monitoring-ready="home"`, делает read-only GET `/api/v1/bootstrap` в том
же context и проверяет HTTP 200, непустой `user.id`, совпадающий email и
`auth_source="local"`. После bounded settle flow отклоняет любой `pageerror`.
Текст browser exception и поля пользователя не возвращаются и не логируются;
оператор получает только фиксированные `step_failed`.

54 screenshot-service tests проходят: success, pageerror-canary, отсутствующий
Home marker, bootstrap 401/503, invalid JSON, отсутствующий id, другой email и
не-local account дают fresh DOWN с безопасной причиной. Mutation-контрпример со
старым flow дал ожидаемые 9 отказов новых сценариев. HomePage unit: 10 passed,
marker закреплён как внутренний monitoring contract.

Полный frontend coverage прошёл: 286 файлов, 2830 тестов; statements 71.2%,
branches 64.71%, functions 60.89%, lines 73%. Lint завершился без ошибок
(21 существующее warning), typecheck, i18n и production build прошли; frontend
diff-coverage — 100% (1 исполняемая строка). Четыре drift-проверки синхронны,
promtool semantic suite успешен, Grafana JSON валиден. No-cache image build и
изолированный hardened-container smoke `/ready`, disabled `/probe` и `/metrics`
прошли. PR #240 смёржен как `b683a8dc`; CI run #1613 завершился 20 success /
9 ожидаемых skips, security run #1614 — 2 success / 3 ожидаемых skips.

Граница: это внутренний local-auth → Home/bootstrap flow через Docker nginx с
Origin/cookie normalization. Он не проверяет Keycloak/OIDC/MFA, внешний
DNS/TLS/proxy/CSP. AT-05 и AT-14 остаются `pending_external`; для SSO нужен
отдельный flow и выделенная минимально-привилегированная учётная запись.


## MON-08 / AT-08 — verified_local, verified_ci, pending_external

Старая `_probe_collabora` обращалась только к странице Nextcloud richdocuments
и считала 302/404 успехом. Новая read-only проба авторизованно получает
`richdocuments.config.wopi_url` через официальный OCS capabilities Nextcloud,
затем отдельным клиентом без Nextcloud Authorization проверяет прямой
`/hosting/capabilities` Collabora/CODE. Успех требует HTTP 200 и непустой
`productVersion`; redirect/login, 401/404, HTML, отсутствующая capability,
небезопасный URL и сетевой отказ дают DOWN. Два запроса разделяют один общий
5-секундный timeout. Поддержаны внешний Collabora и встроенный CODE
`proxy.php?req=`.

Локально: 26 целевых MON-08 tests; расширенный integration-health/readiness
набор — 62 passed; полный Ruff/format/mypy — 927 файлов; backend diff-coverage
100% (45 строк); четыре drift-проверки синхронны. Mutation старой реализации
ожидаемо дал 2 отказа на 302/404 (1 контрольный 401 прошёл как DOWN), поэтому
regression-тесты различают исходный ложный зелёный сигнал.

Граница: проверяются конфигурация Nextcloud Office и свежий ответ Collabora
capabilities. Реальный документ, WOPI callback/allowlist, federation display
name, browser editor и group restriction не проверялись. Runtime с настоящими
Nextcloud credentials остаётся `pending_external`.


## Этап E — verified_local (браузерная приёмка на изолированном стенде)

Обзорный экран «Portal — Overview» перестроен по §8.1: верхний блок отвечает на
«что не работает / кто затронут / насколько свежи данные / что делать»:
статусы возможностей сотрудников (вход, API, почта, 1С, Keycloak/Nextcloud/
Collabora/SMTP/ERP), счётчик + таблица активных тревог (ALERTS, русские
колонки Тревога/Важность/Сервис), здоровье наблюдения (7 компонентов +
storage-collector + external blackbox «Не настроено»), текстовый блок dead-man
pending. Русские тексты состояний вместо DISABLED/STALE/DOWN/UP; noValue
«Нет данных» в fieldConfig.defaults (options.noValue Grafana игнорирует —
найдено при приёмке); у state-панелей нейтральный базовый порог, чтобы «Нет
данных» не был красным/зелёным. Честные подписи: «SMTP: сетевая проверка (не
доставка)», «Доля успешных HTTP-ответов — техническая, не доступность
портала». Ссылки: Runbook, Logs, Infrastructure, Storage, monitoring.md.

«Топ-10 таблиц по размеру» (storage) переведён на instant-запрос с русскими
колонками Таблица/Размер — показывает текущий срез (audit_log_2026_08 1.97MiB,
users, email_outbox…), а не временные ряды (дефект из аудита).

**Runbook** `docs/runbooks.md`: 14 групп алертов по схеме §8.3 (что произошло →
что не работает у сотрудников → что посмотреть сначала (только read-only
команды) → как проверить восстановление → когда звать специалиста) +
инструкция владельцу (ежедневный чек-лист 2 мин, отличия
critical/warning/no-data, проверка доставки). Добавлен в роутер
docs/README.md и в ссылки дашборда.

**CI** (часть MON-15): job monitoring-config получил шаг
`scripts/validate-grafana.py` — JSON, уникальность panel id, границы сетки 24
колонок, известные datasource UID, затем promtool парсит все 98 expr
дашбордов (эмит как rules-файл). Локально: 4 дашборда OK, promtool exit 0.

**Браузерная приёмка** (изолированный Grafana 13.1.3 на :3002 с provisioning
из рабочей ветки, datasource — локальный Prometheus тестового стенда, юзерский
стек не менялся): 1440px dark — реалистичная смешанная картина (5 живых
warning-тревог: Watchdog, EmailOutboxDLQ, StorageCollectorStale,
AlertmanagerNotificationsFailed, Keycloak integration down; «Данные устарели»,
«Работает», «Готов», DLQ=3); 1440px light (?theme=light); 768px и 390px —
панели складываются, ссылки переносятся; полностью отсутствующие данные
(диапазон 2020) — «Нет данных» везде, счётчик тревог 0 зелёным (честно:
в диапазоне тревог нет); таблица storage на реальных данных. Несколько
одновременных тревог — покрыто живым состоянием. Длинные названия — проверено
поведение обрезки, полные названия в описаниях/тултипах и runbook.

Граница: production-дашборды и реальный внешний доступ — pending_external;
панель «Вход сотрудников» покажет состояние после deploy волны (текущий стенд
на старом образе без новых метрик — «Нет данных» честно).

## Этап G (частично) — verified_test_runtime: волна MON-01..13/E на живом тест-контуре

2026-09-10 владелец пересобрал и перезапустил тест-стек (app + monitoring overlay).
Проверка по живому Prometheus/логам (все значения честные, без подгонки):

- **Свежесть (MON-06)**: «Метрики» = «Свежие» (generated_at заполняется, порог 120с);
  после рестарта PortalSyntheticProbeStale корректно вспыхнул до первой
  завершённой пробы и погас — «после рестарта старый зелёный не сохраняется»
  работает в рантайме.
- **Synthetic с реальной учёткой (MON-05/AT-15)**: probe.done ok=true, 4.1с;
  portal_synthetic_probe_up=1, result_available=1 — runtime-хвост закрыт на
  тест-контуре (внешний SSO/TLS остаётся pending_external).
- **Интеграции (MON-08)**: Collabora = up (новый зонд с реальными OCS
  capabilities + /hosting/capabilities); **Keycloak = down, PortalIntegrationDown
  firing — контейнер keycloak в тест-контуре отсутствует**, проба честно
  подсвечивает (вопрос владельцу: отключить интеграцию в тестовых настройках
  или поднять IdP).
- **Пул БД (MON-09)**: portal_db_pool_size/in_use/idle и
  db_pool_update_timestamp свежие; per-pid лейблы проявляются только при
  нескольких uvicorn-воркерах (прод-сценарий, покрыт AT-09 тестом).
- **Storage collector (MON-12)**: portal_storage_collector_error=0, новые
  метрики читаются.
- **Dead-man (MON-13)**: rendered alertmanager содержит маршрут
  Watchdog → deadman-webhook; приёмник no-op (ALERT_DEADMAN_WEBHOOK_URL пуст —
  pending §14).
- **MON-01**: спот-чек свежих логов backend — совпадения по «password» только
  имена колонок SQL, значений нет.
- Активные тревоги тест-контура: Watchdog (маяк), PortalIntegrationDown
  (keycloak — реальность), PortalEmailOutboxDLQ (старые недоставленные письма
  тестовой среды — уборка на усмотрение владельца).

Граница: production-приёмка (§14) остаётся pending_external; per-pid пул и
множество воркеров — прод-сценарий.

## MON-18 / MON-20 — verified_test_runtime (изолированный стенд)

### MON-18: Alloy restart/replay (эксперимент, isol: mon18-loki + mon18-emitter + mon18-alloy v1.18.1, та же версия, что прод)

Эмиттер пишет JSON-линии 1/сек (сквозные номера n, свой ts); Alloy по
`loki.source.docker` (фильтр по имени), пайплайн как прод (docker → json →
timestamp RFC3339Nano skip). Замеры по сквозным номерам в Loki:

| Сценарий | Результат |
|---|---|
| A1: SIGKILL + start ТОГО ЖЕ контейнера | возобновление с сохранённых offsets: линии простоя (20 шт.) доставлены, 0 дублей, 0 дыр |
| A2: `docker rm -f` + recreate (состояние потеряно — каждый апдейт оверлея) | **Alloy перечитывает лог контейнера с начала**; Loki отбраковывает старые линии как out-of-order. Нетто-результат: 0 потерь, 0 дублей (каждый n ровно 1 раз — проверено count_over_time по n=100/290/350); за один recreate Loki принял +845 линий при +61 сохранённых |
| Том для /var/lib/alloy | **НЕ влияет**: docker-source не хранит offsets там; перечитывание с начала — присущее поведение (проверено двумя recreate подряд с томом) |
| B: graceful `docker restart` | то же, что A1 — чистое возобновление |
| Timestamp после replay | линии из downtime лежат со СВОИМ JSON-временем (совпадение до секунды) |
| Дедуп Loki | отсутствует (дважды запушенная идентичная запись хранится дважды) — корректность обеспечивается OOO-отбраковкой Loki |

**Выводы/рекомендации:** (1) данные не теряются и не дублируются во всех
сценариях — поведение подтверждено, не «по документации»; (2) цена recreate —
ре-репуш всей истории контейнера (на проде ограничена ротацией json-file
50МБ×5 ≈ 250МБ/контейнер) + временный лаг новых линий на catch-up; (3) том для
Alloy под эту проблему НЕ добавлять (не помогает, проверено); (4) при
out_of_order acceptance ≠ default поведение изменилось бы (появились бы
дубли) — не включать без пере-теста; (5) второй Alloy-инстанс на тот же
docker-socket недопустим.

### MON-20: сверка единиц/порогов/доступа

- `PortalPGWraparound` использует `pg_database_wraparound_age_datfrozenxid_seconds > 2592000` — СЕКУНДЫ с последнего freeze, порог 30 дней; единицы корректны. Д docs/monitoring.md строка «XID возраст > 1.5e9» была устаревшей — исправлена на фактическую.
- `PortalContainerRestartLoop`: `changes(container_start_time_seconds[15m]) > 3` — единицы/окно корректны.
- **Находка (безопасность):** `GF_SECURITY_ADMIN_PASSWORD` имеет дефолт `admin` в compose, а `GRAFANA_BIND` по умолчанию `0.0.0.0:3001` → Grafana доступна всей LAN с admin/admin, если пароль не задан. `.env.example` исправлен (пустой дефолт + громкий комментарий), в docs/monitoring.md добавлена грабля-проверка. Владельцу: убедиться, что в действующем `.env` пароль не admin.
- `/metrics` наружу через nginx не отдаётся (проверка вернула соединение-ошибку — путь закрыт).

## MON-19 — verified_ci (infrastructurally ready; фактический pull — при prod-деплое)

`portal-storage-collector` переведён на общий механизм образов (ADR-045/046/049):
- CI-матрица publish: 7-й образ (context ./monitoring/node-exporter-textfile), теги sha-<sha>/latest/semver, trivy-скан автоматом;
- monitoring-overlay: `image: ${IMAGE_PREFIX:-}portal-storage-collector:${IMAGE_TAG:-latest}` + build-блок (dev собирает локально — поведение dev не изменилось: IMAGE_PREFIX пуст, IMAGE_TAG=latest = прежнее `portal-storage-collector:latest`);
- prod: IMAGE_PREFIX=forgejo.mage.ru/mage/ (профиль) → pull готового образа; local-build заблокирован setup.sh;
- monitoring/README.md: обновлён раздел обновления.

Граница: фактический pull образа из registry выполняется на prod-контуре при релизе
(этап G / production-приёмка); CI-публикация подтверждается первым push в main
после мёржа (появится portal-storage-collector:sha-<sha> в registry).

## Остальные находки


Дополнительно (review): radon-гейт CI забраковал `_probe_collabora` (CC 24, rank D) — функция декомпозирована на `_ocs_meta_ok` / `_extract_wopi_url` / `_collabora_version` / `_fetch_wopi_url` / `_collabora_capabilities_ok` без изменения поведения; 49 тестов test_integration_health.py зелёные, `radon cc app -n D` чист, ci_lint (ruff/format/mypy) пройден.
## MON-13 — verified_local, verified_ci; внешняя приёмка pending_external

Watchdog (всегда-firing) маршрутизирован в выделенный приёмник
`deadman-webhook` — первый route в дереве (email админам не уходит);
`group_wait: 0s`, `repeat_interval: 4m`, `group_interval: 5m` (пинги каждые
~5 мин), `send_resolved: true`. `ALERT_DEADMAN_WEBHOOK_URL` (`.env` → overlay
compose → render) при пустом значении вырезает webhook-блок рендером
(маркеры #@deadman-begin/end по образцу #@matrix) — приёмник становится no-op
(как info-null), Watchdog не спамит email. Контракт маяка зафиксирован
promtool-тестом «Watchdog always fires» (горит даже при up=0 — пропажа маяка
на внешнем приёмнике однозначно означает отказ Prometheus/Alertmanager).
CI amtool-джоб валидирует ОБЕ ветки рендера (webhook задан / пуст).

Локально: amtool check-config SUCCESS на обе ветки рендера
(prom/alertmanager:v0.33.1, как CI); структурная проверка rendered YAML —
Watchdog-маршрут первый и ведёт только в deadman-webhook; в no-op ветке
приёмник пуст; promtool test rules SUCCESS (включая новый watchdog-сценарий).
Документация: docs/monitoring.md §«Dead-man контроль пропажи мониторинга»
(покрытие отказов Prometheus/Alertmanager/хоста, grace ≥ 3× интервала),
.env.example.

Граница: выбор внешнего сервиса (healthchecks.io-совместимый / self-hosted в
разрешённом периметре), реальный webhook-приёмник и сквозная проверка «отказ →
внешний сигнал» (включая отказ SMTP и всего стенда, §7.3) — pending_external,
требуется решение владельца (ТЗ §14, вопросы 1–2).

## MON-12 — verified_local, verified_ci; приёмка на реальном хосте pending_external

collect.sh: (1) лейбл `container` — уникальное имя контейнера + лейблы
`project`/`service` из compose-лейблов: два compose-проекта с одинаковым
именем сервиса и две реплики одного сервиса дают различные labelset'ы вместо
дублей рядов, ломавших textfile-scrape; (2) неверный корень
(`PORTAL_HOST_PATH` опечатка / нет маунта) публикует
`portal_storage_collector_error{reason="root_missing"} 1` и СОХРАНЁННУЮ
прошлую свежесть вместо «свежих нулей»; (3) нечитаемая существующая папка
(права) считается через `portal_storage_collector_read_errors` — du на
нечитаемой папке может напечатать частичный размер, поэтому решение по коду
возврата du, а не по пустоте вывода; пустая папка — легитимный 0;
(4) `last_run_seconds` обновляет только успешный прогон — при root_missing
или read_errors>0 хранится прошлое значение, `PortalStorageCollectorStale`
честно срабатывает при деградации. Публикация атомарная (mv) в обеих ветках,
включая ошибочную.

Локально: bats-набор `tests/setup/test_storage_collector.bats` — 7 сценариев
§9 ТЗ (happy path с новыми лейблами; пустая папка = 0 без ошибки;
несуществующий root с сохранением last_run; два проекта с одинаковым
сервисом; две реплики; отсутствие прав — chmod 000, skip под root;
не-compose контейнер с пустыми project/service); shellcheck --severity=warning
чист. Графан-запросы портала агностичны к новым лейблам
(`topk(5, portal_storage_folder_bytes)`, bare-метрика, legend `{{ container }}`).

Граница: фактический scrape node-exporter'ом двух compose-проектов на реальном
хосте и сверка с prod registry/semver-политикой локальной сборки образа
(MON-19) — `open`/`pending_external`.

MON-14 остаётся `pending_external` (только значение BLACKBOX_TARGETS на проде — инфраструктура готова); MON-15-остаток (исполнение запросов на живом прометее прод-контура). MON-18/20 закрыты; бэкапы вне периметра (решение владельца). MON-05/AT-15 смёржены через PR #240; MON-08/AT-08 — через PR #241; MON-09/AT-09 — через PR #242. Runtime synthetic и Collabora с настоящими учётными данными остаются `pending_external`.

## PR и CI

- PR #237 смёржен как `a22627c1`; CI run #1601 — 20 success,
  9 ожидаемых release/publish skips; security run #1602 — 2 success,
  3 ожидаемых skips.
- PR #238 смёржен как `037f7491`; CI run #1605 — 20 success,
  9 ожидаемых release/publish skips; security run #1606 — 2 success,
  3 ожидаемых skips. Synthetic lifecycle/freshness получил полную удалённую
  проверку; запуск с настоящими credentials остаётся `pending_external`.
- PR #239 смёржен как `2ec5f864`; CI run #1609 — 20 success, 9 ожидаемых
  release/publish skips; security #1610 — 2 success, 3 ожидаемых skips.
- PR #241 (MON-08) смёржен как `da88076c` (головной `2817c41e`): CI #1617 + security #1618, combined status `success`, 22 success / 8 ожидаемых skips / 0 failed.
- PR #242 (MON-09) смёржен как `da749f5d` (головной `1ff2e80b`): CI #1621 + security #1622, combined status `success`, 22 success / 8 ожидаемых skips / 0 failed.
- PR #243 (MON-13 + MON-12) смёржен как `24dfccf6` (головной `a680a695`): CI #1629 + security #1630, combined status `success`, 22 success / 8 ожидаемых skips / 0 failed. Первый прогон ловил ФС-зависимость `du -bs` — apparent-size директории на overlayfs.
- PR #244 (handoff волны) смёржен как `2e41e467` (головной `bf306e67`): CI #1633 + security #1634, combined status `success`, 22 success / 8 ожидаемых skips / 0 failed.
- PR #240 смёржен как `b683a8dc`; CI run #1613 — 20 success / 9 ожидаемых skips; security #1614 — 2 success / 3 ожидаемых skips.

- PR #236 создан пользователем: `https://forgejo.mage.ru/mage/portal/pulls/236`. Forgejo REST API 2026-09-08 снова доступен с настроенным токеном.
- Run на `dcf17eec`: backend lint упал на Ruff I001 в новом security-тесте. На новом HEAD `25d8f728` backend lint, unit/security и локальные проверки исправления прошли; импорт отсортирован.
- Vitest дважды подряд дал одинаковые 6 файлов/8 отказов: независимые page/router tests упёрлись в 15 s, остальные 280 файлов/2821 тест прошли. Причина — чрезмерный автоматический параллелизм jsdom на shared runner. `maxWorkers=4` применяется только при `CI`; полный локальный CI-equivalent coverage-run прошёл: 286 файлов, 2829 тестов, 0 Vue warnings, 52.46 s. Run #1589 подтвердил зелёный `frontend / vitest`, но был отменён следующим push до завершения всех jobs.
- Run #1591 воспроизвёл инфраструктурную гонку двух Python-jobs: `pip install -e` одновременно изменял общий `/opt/hostedtoolcache/.../portal_backend-1.0.0.dist-info`. После каждого `setup-python` добавлен job-локальный `.venv-actions`. Run #1593 на `abf502ae` завершился success: 20 jobs успешны, 9 release/publish jobs ожидаемо skipped; backend lint, 5253 unit/security, 700 integration + 2 nightly skips, Vitest, Playwright, compose, monitoring и drift зелёные. Security run #1594: pip/npm audit и Trivy успешны, weekly/CodeQL ожидаемо skipped.
- Локальная итоговая выборка изменённых backend-модулей: 139 passed, coverage 85.23%; diff coverage всей ветки 100% (115 строк). Per-probe unit: 108 passed; отдельный реальный Redis переход: 1 passed. Полные ruff/format/mypy, четыре drift-проверки и promtool semantic rules прошли.
- Локально backend/worker-часть MON-01 и false-success часть MON-02 проверены. Production-инцидент, screenshot-service и точная причина ARQ cancellation остаются открытыми. Merge остаётся пользователю.
