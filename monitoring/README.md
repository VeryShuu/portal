# Observability stack — reference configs

Reference конфигурация полного observability-стека для портала:
**Prometheus + Alertmanager + Grafana + Loki + Alloy**.
**Не** подключена к основному `docker-compose.yml` — поднимается отдельным
overlay, чтобы не тащить тяжёлые образы (~900 МБ суммарно) в базовый деплой.

> **Подробности:** `../docs/monitoring.md` (backend-экспорт метрик, токен-защита
> `/metrics`, cross-process snapshot, централизованные логи §9). Этот каталог —
> **consumer-сторона**: scrape-конфиг, сбор логов, alerting-правила, дашборды.
> **Обоснование выбора:** ADR-044 (Loki vs ELK, Alloy vs Promtail, overlay-подход).

## Структура

```
monitoring/
├── README.md                              ← этот файл
├── prometheus.yml                         ← scrape-конфиг (portal-backend + self)
├── loki/
│   └── config.yml                         ← single-binary Loki (retention 30d, compactor)
├── alloy/
│   └── config.alloy                       ← сбор Docker-логов → Loki (discovery + JSON)
├── alerts/
│   ├── portal.yml                         ← alerting rules (PromQL)
│   └── alertmanager.yml                   ← routing + email-receivers (SMTP-relay)
├── grafana/
│   ├── portal-overview.json               ← дашборд метрик (RED + audit + worker)
│   ├── portal-logs.json                   ← дашборд логов (ошибки, объём, request_id)
│   └── provisioning/
│       ├── datasources/
│       │   ├── prometheus.yml             ← auto-provision Prometheus (uid=prometheus)
│       │   └── loki.yml                   ← auto-provision Loki (uid=loki)
│       └── dashboards/portal.yml          ← auto-provision дашбордов из JSON
└── docker-compose.monitoring.yml          ← overlay для `docker compose -f ...`
```

## Запуск (полный стек — метрики + логи + алерты + UI)

```bash
docker compose \
  -f docker-compose.yml \
  -f monitoring/docker-compose.monitoring.yml \
  up -d prometheus alertmanager grafana loki alloy
```

Сервисы подключаются к сети `portal_internal` (см. основной `docker-compose.yml`),
поэтому видят `backend`, `redis`, `postgres` и друг друга. Alloy дополнительно
монтирует Docker socket (read-only) для discovery контейнеров и attach к stdout/stderr.

UI (на хосте, проброшены на `127.0.0.1` — через SSH-туннель или reverse-proxy):

| Сервис | Порт | Назначение |
|---|---|---|
| Grafana | `:3000` | Единый UI: метрики + логи. admin/admin (смена при первом входе) |
| Prometheus | `:9090` | Метрики: targets, query (PromQL), alert state |
| Alertmanager | `:9093` | Состояние алертов, silences, тест отправки |
| Loki | `:3100` | API логов (обычно через Grafana, напрямую — для отладки) |
| Alloy | `:12345` | UI pipeline сборщика (inspect tailers, debugging) |

### Exporter'ы (инфраструктурные метрики)

Prometheus скрейпит не только backend, но и 4 exporter'а, подключённых к
`portal_internal` (видят `postgres`/`redis`/`nginx` по DNS). Секреты
(`POSTGRES_PASSWORD`, `REDIS_PASSWORD`) интерполируются из `.env` автоматически.

| Exporter | Порт | Источник | Что даёт |
|---|---|---|---|
| postgres-exporter | `:9187` | `prometheuscommunity/postgres-exporter:v0.20.1` | Пул соединений, cache hit ratio, XID wraparound, размер БД, долгие транзакции, дедлоки |
| redis-exporter | `:9121` | `oliver006/redis_exporter:v1.77.0` | Память/evictions, клиенты, keyspace hit rate |
| node-exporter | `:9100` | `prom/node-exporter:v1.12.1` | Диск (критично — `/data/photos`), CPU, RAM, load |
| nginx-exporter | `:9113` | `nginx/nginx-prometheus-exporter:1.4.0` | Active connections, request rate (через `stub_status`) |

Nginx отдаёт `stub_status` на `http://nginx:80/stub_status` (только из сети
`172.16.0.0/12` — внутренний Docker bridge), см. `nginx/templates/proxy_locations.conf.tmpl`.
`request_time`-перцентили остаются в Loki (JSON access-log), не в stub_status.

### Дашборды Grafana

| Дашборд | UID | Покрытие |
|---|---|---|
| Portal — Overview | `portal-overview` | RED backend (rate/errors/latency), audit pipeline, ARQ-задачи (jobs/duration/failures), бизнес-метрики (SSE, активные юзеры, KB/news/photos) |
| Portal — Logs | `portal-logs` | Ошибки, slow-nginx, 5xx, трассировка по `request_id` |
| Portal — Infrastructure | `portal-infra` | PostgreSQL, Redis, Host (диск/CPU/RAM), Nginx — метрики из exporter'ов |

## Настройка scrape-токена

Backend защищает `/metrics` токеном из `system.json::metrics_token` (см.
`docs/monitoring.md` §3, `middleware/metrics.py::_require_metrics_token`),
принимаемым через `Authorization: Bearer` (этот путь настраивает Prometheus)
**или** `X-Metrics-Token` (для ad-hoc `curl`). Если токен задан, передаём
через env:

```bash
PORTAL_METRICS_TOKEN="$(jq -r .metrics_token // empty system_data/settings/system.json)" \
  docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d prometheus
```

Пустой токен → `/metrics` открыт (допустимо в закрытом периметре/VPN).

## Email-доставка алертов

`alertmanager.yml` шлёт алерты админам через **прямой SMTP-relay** (env-параметризуемые
`${ALERT_SMTP_*}`), независимый от portal `email_outbox` — критично: алерты уходят
даже при падении backend/worker. Переменные задаются в `.env` (см. `.env.example`,
секция Observability). При пустом `ALERT_SMTP_HOST` алерты видны только в UI Alertmanager.

Тест отправки алерта:
```bash
amtool alert add PortalBackendDown alertmanager=http://localhost:9093 \
  severity=critical 'description=test alert'
```

## Примеры LogQL-запросов (в Grafana → Explore → Loki)

```logql
# Ошибки backend/worker за последний час
{service=~"portal-backend|portal-worker", level=~"error|critical"}

# Сквозная трассировка по request_id (nginx-access ↔ backend-request)
{container=~"portal-.*"} | json | request_id="<id>"

# Медленные запросы nginx (> 2с)
{container="portal-nginx-1"} | json | request_time > 2

# 5xx ошибки nginx
{container="portal-nginx-1"} | json | status >= 500
```

## Проверка конфигов

```bash
# Overlay compose:
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml config --quiet

# Prometheus (нужен promtool):
docker compose -f monitoring/docker-compose.monitoring.yml run --rm prometheus \
  promtool check config /etc/prometheus/prometheus.yml

# Alert rules (PromQL-синтаксис):
docker compose -f monitoring/docker-compose.monitoring.yml run --rm prometheus \
  promtool check rules /etc/prometheus/rules/portal.yml

# Alertmanager:
docker run --rm -v ./monitoring/alerts/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro \
  -e ALERT_SMTP_HOST=localhost -e ALERT_SMTP_PORT=25 -e ALERT_SMTP_FROM=a@b \
  -e ALERT_ADMINS_EMAIL=c@d --entrypoint amtool prom/alertmanager:v0.27.0 \
  check-config /etc/alertmanager/alertmanager.yml

# Alloy (River-синтаксис):
docker run --rm -v ./monitoring/alloy/config.alloy:/etc/alloy/config.alloy:ro \
  --entrypoint alloy grafana/alloy:v1.18.0 fmt --test /etc/alloy/config.alloy
```

## Грабли

- **Loki 3.6+ и Alloy не содержат `wget`/`curl`** (busybox убран, upstream
  issues grafana/loki#20149, grafana/alloy#477). Встроенный HTTP-healthcheck
  невозможен — убран. Готовность: `restart` + ручная проверка с хоста.
- **Cross-process snapshot:** гейджи `portal_audit_queue_depth`,
  `portal_audit_processing_depth`, `portal_active_users_last_1h` обновляются
  ARQ-cron'ом `refresh_custom_metrics` раз в 30с → пишутся в Redis
  `metrics:snapshot` → подтягиваются в API-process при scrape. Лаг ≤30с —
  поэтому все алерты на эти гейджи имеют `for: 5m` минимум.
- **Гейджи без воркера «замерзают».** Если `portal-worker` не запущен,
  `metrics:snapshot` не обновляется → кастомные метрики показывают
  устаревшие значения. Алерт `PortalWorkerStale` поймает это по отсутствию
  изменений gauge за 3 мин.
- **`request_id` — НЕ Loki-лейбл** (high-cardinality). Лейблы только `service`,
  `level`, `container`, `compose_service`. Поиск request_id через LogQL `| json`.
- **`/health` и `/ready` исключены** из RED-метрик (см. `middleware/metrics.py`),
  поэтому в Prometheus их не видно — это нормально, они для оркестратора.
- **Фиксированные UID datasource** (`uid: loki`, `uid: prometheus`) обязательны —
  без них Grafana генерирует случайные UID, дашборды не находят datasource'ы.
