# Фича: Observability — закрытие пробелов аудита 2026-07-21

> **Когда читать:** возобновляешь работу по расширению observability-стека
> портала (логирование/аудит/метрики/nginx) — этот план хранит контекст между
> сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> **Источник:** разбор подсистем логирования/аудита от 2026-07-21.

## Цель

Закрыть пробелы, выявленные разбором observability-стека:
- 🟠 **N1 — нет alerting-слоя:** Prometheus-метрики экспортируются, но
  consumer-стороны (alerting/дашборды) нет ни в репо, ни в документации.
- 🟠 **N2 — корреляция request_id обрывается на nginx:** backend генерирует
  `X-Request-Id` и биндит в contextvars, но `system_data/nginx/nginx.conf`
  пишет access-log без этого идентификатора → связать nginx-access и
  backend-request невозможно.
- 🟡 **N3 — таксономия событий (113 строк) не формализована:** опечатка в
  `event_type="links.vistied"` молча создаст новый тип; нет compile-time guard.
- 🟡 **N4 — `audit.log()` — мёртвый код:** синхронный INSERT в БД (через
  изолированную сессию), нет runtime-callers, но есть 7 unit-тестов.
  Документацией не описан. Удалять нельзя (решение пользователя) —
  задокументировать как deprecated fallback.
- 🟡 **N5 — middleware/logging.py без характеризации:** correlation-flow,
  slow-request branching, context-clear-on-exception тестируются косвенно.
- 🟢 **N6 — косметика:** `_sync_pg_url` повторяется 3×, bare `except` в
  `audit.log`, порядок секций `audit.md` сбит.

Позитив: архитектура аудита/логирования production-grade (outbox-pattern с
LMOVE+lock, structlog с redaction/PII/truncation, cross-process Prometheus
snapshot, Sentry scrub_sensitive). Доработки — точечные, на стыке с
инфраструктурой.

## Решения по ходу

- **2026-07-21:** observability-стек оформляем как **reference-конфиги в
  `monitoring/`** — БЕЗ правок основного `docker-compose.yml`. Команда решает
  сама, подключать ли через overlay (`docker-compose.monitoring.yml`) или
  внешним scrape. Причина: не ломать prod-деплой, не тащить тяжёлые образы
  (prometheus/grafana) в базовый compose.
- **2026-07-21:** `audit.log()` НЕ удаляем — у него 7 unit-тестов, и это
  потенциальный fallback-API при недоступности Redis (хотя `push_audit_event`
  и так ловит ошибки). Помечаем `@deprecated` в docstring + обновляем
  `docs/audit.md`. Удаление — отдельное решение пользователя.
- **2026-07-21:** event-type taxonomy — `StrEnum` (Python 3.12, уже в стеке),
  не `Literal`. Причина: итерация по значениям (для/docs/генерации), и
  mypy-совместимость с существующими call-sites `event_type="news.created"`.
- **2026-07-21:** nginx `log_format` живёт в `system_data/nginx/nginx.conf`
  (volume, под git — `system_data/` tracked). Это **не** sidecar-template;
  правки применяются через restart `portal-nginx`. Sidecar
  (`nginx/templates/`) править не нужно — он рендерит server-block, не http-block.

## Чеклист (DoD)

### Приоритет 1 — alerting + корреляция (1–1.5 дня)

- [ ] **P1.1 Nginx: проксирование `X-Request-Id` + json_combined с request_id.**
      `proxy_locations.conf.tmpl`: `proxy_set_header X-Request-Id $http_x_request_id;`
      (если нет — генерировать). `system_data/nginx/nginx.conf::log_format`:
      добавить поле `"request_id":"$http_x_request_id"`. Проверить через
      `docker compose restart nginx` + curl с заголовком.
- [ ] **P1.2 Reference-стек Prometheus/Alertmanager.**
      Создать `monitoring/` (README, `prometheus.yml` со scrape portal-backend
      на `/metrics` + token, `alerts/portal.yml` с правилами):
      - `PortalWorkerDown` — `arq:heartbeat` не обновлялся >2 мин.
      - `PortalAuditQueueBacklog` — `portal_audit_queue_depth > 1000` >5 мин.
      - `PortalAuditFlushStuck` — `portal_audit_processing_depth > 0` >10 мин.
      - `PortalHighErrorRate` — `http_requests_total{status=~"5.."}` rate.
      - `PortalReadinessFailing` — `up{job="portal"} == 0` или готовность.
      - `alertmanager.yml` — stub routing (webhook/email placeholder).
- [ ] **P1.3 Grafana dashboard.**
      `monitoring/grafana/portal-overview.json` — минимальный: RED-метрики
      (rate/latency/error), audit queue depth, worker heartbeat, active users,
      фото-хранилище. + `provisioning/` для auto-load.
- [ ] **P1.4 Overlay docker-compose.monitoring.yml** (опционально, для команды).
      Поднимает prometheus + alertmanager + grafana одной командой:
      `docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml --profile monitoring up -d`.
- [ ] **P1.5 Обновить `docs/monitoring.md`:** секция §8 «Alerting и Grafana»
      со ссылками на `monitoring/` и инструкцией запуска.
- [ ] **P1.6 DoD:** nginx-restart локально проверен (если доступен docker);
      конфиги валидны (`promtool check config`, `amtool check-config`);
      `ruff && mypy && pytest tests/unit` зелёные (P2/P3).

### Приоритет 2 — устойчивость (0.5 дня)

- [ ] **P2.1 Event-type taxonomy → `app/services/audit_events.py`** (`StrEnum`).
      Перенести 113 строк в типобезопасный enum. Обновить call-sites (поиск по
      `event_type="..."`) — заменить литералы на `EventType.XXX`. Mypy-проверка.
      Не ломать `analytics_repo._DOWNLOAD_EVENTS` и т.п. (они работают со
      строками — оставить как есть, но сослаться на enum в комментарии).
- [ ] **P2.2 Характеризующие тесты `middleware/logging.py::request_logging`.**
      `tests/unit/test_request_logging_middleware.py`:
      - Принятый `X-Request-Id` прокидывается в ответ.
      - При отсутствии — генерируется новый (uuid-формат).
      - Слишком длинный (>128) — игнорируется, генерируется новый.
      - Status 5xx → `logger.error`, 4xx → `logger.warning`, 2xx → `logger.info`.
      - Slow request (>= `log_slow_request_ms`) → warning.
      - Exception в downstream → `logger.exception`, context очищается.
- [ ] **P2.3 DoD:** новые тесты зелёные; mypy проходит на `audit_events.py`.

### Приоритет 3 — косметика (0.5 дня)

- [ ] **P3.1 `_sync_pg_url()` helper** в `worker/tasks/audit.py` (DRY ×3).
- [ ] **P3.2 `audit.log()`:** `@deprecated` в docstring; обновить
      `docs/audit.md` §6 — упомянуть как deprecated fallback, основной путь
      `push_audit_event`.
- [ ] **P3.3 Порядок секций `docs/audit.md`:** переместить §«Безопасность»
      перед §«Тесты» (по `_TEMPLATE.md`).
- [ ] **P3.4 DoD:** `ruff check . && mypy app && pytest tests/unit` зелёные.

## Грабли / контекст

- **`system_data/nginx/nginx.conf` — volume, но под git.** Правки применяются
  через `docker compose restart nginx` (или `docker compose up -d nginx` после
  изменения файла на хосте). Sidecar `nginx-config` его **не** рендерит — он
  работает с `nginx/templates/` (server-block).
- **`X-Request-Id`单向.** Сейчас балансер → backend (если шлёт). Добавляем
  проксирование в `proxy_locations.conf.tmpl` И генерацию в nginx, если входящий
  заголовок пустой (`map "" $req_id { ... default $request_id; }` — но nginx
  1.11+ имеет `$request_id` из коробки, используем его).
- **Prometheus scrape-токен.** В `prometheus.yml` шлём через `bearer_token` или
  `params` + `authorization`. Если `metrics_token` не задан — `/metrics` открыт
  (закрытый периметр/VPN); reference-конфиг должен это учитывать.
- **Cross-process snapshot:** гейджи типа `portal_audit_queue_depth` знает
  **воркер** (через `metrics:snapshot` в Redis), а scrape идёт в **API**. В
  Prometheus видим значения с задержкой ≤30с (cron `refresh_custom_metrics`).
  Алерты на гейджи — с `for: 5m` минимум, чтобы не триггерить на лаг снапшота.
- **`StrEnum` — Python 3.12+** (стек зафиксирован). `from enum import StrEnum`.
  Обратная совместимость: `EventType.AUTH_LOGIN == "auth.login"` → `True`.
- **`audit.log()` НЕ удалять в этой задаче** — есть 7 тестов, это рискованное
  изменение без явного согласия пользователя. Только docstring-deprecation.

## Handoff (заполняется в конце каждой сессии)

```
СДЕЛАНО: все 11 пунктов плана закрыты в одной сессии.
  - P1.1 Nginx: log_format json_combined + request_id (system_data/nginx/nginx.conf);
    proxy_set_header X-Request-Id $req_id в proxy_locations.conf.tmpl (api/health/SSE/federation).
    Map $http_x_request_id → $req_id (fallback на nginx $request_id).
  - P1.2 monitoring/prometheus.yml (scrape portal-backend + self),
    monitoring/alerts/portal.yml (8 правил: BackendDown/HighErrorRate/AuditQueue*,
    WorkerStale/ArqJobsFailing/HighLatency/PhotoStorage),
    monitoring/alerts/alertmanager.yml (routing stub).
  - P1.3 monitoring/grafana/portal-overview.json (14 панелей: RED, audit pipeline,
    worker health, content counts) + provisioning (datasources/dashboards).
  - P1.4 monitoring/docker-compose.monitoring.yml (overlay, профильная сеть
    portal_internal), валидирован `docker compose config --quiet`.
  - P1.5 docs/monitoring.md +§7 «Alerting и Grafana» (таблица алертов, инструкция
    запуска), обновлён обзорный блок +§8 грабли про nginx access-log request_id.
  - P2.1 backend/app/services/audit_events.py — EventType StrEnum (114 типов),
    + backend/tests/unit/test_audit_events.py (6 тестов) — нашёл и зарегистрировал
    пропущенный 'files.file_shared' (literal в IfExp — grep его не видел).
  - P2.2 backend/tests/unit/test_request_logging_middleware.py — 11 характеризующих
    тестов (correlation id, status→level, slow-request branch, exception-flow,
    response header).
  - P2.3 backend/app/services/audit.py:log() — docstring @deprecated;
    docs/audit.md §6 — альтернативный путь + note про EventType enum.
  - P3.1 _sync_pg_url() helper в worker/tasks/audit.py (DRY ×3 → 1).
  - DoD: ruff check ✓, mypy app ✓ (350 файлов), pytest tests/unit ✓ (3706 passed,
    17 новых), все YAML/JSON валидированы.
В РАБОТЕ: —
ДАЛЕЕ: пользователь коммитит; всё готово к мёржу.
ОТКРЫТЫЕ ВОПРОСЫ:
  - Подключать ли monitoring/ как overlay в проде? Решает команда на деплое
    (instructions в monitoring/README.md).
  - alertmanager.yml — заглушка receivers (webhook-placeholder). Реальные
    transport'ы (email/Slack/Telegram) настраивает команда под свою инфру.
  - audit.log() удаление — отдельное решение пользователя (сейчас deprecated,
    7 unit-тестов, нет runtime-callers).
  - Портал не пересобирался — nginx-правки (P1.1) применятся после
    `docker compose restart nginx` (system_data — volume под git, не образ).
КОММИТ: см. ниже
```
