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
├── prometheus.yml                         ← scrape-конфиг (portal-backend + self + loki)
├── loki/
│   └── config.yml                         ← single-binary Loki (retention 30d, compactor)
├── alloy/
│   └── config.alloy                       ← сбор Docker-логов → Loki (discovery + JSON)
├── alerts/
│   ├── portal.yml                         ← alerting rules (PromQL)
│   ├── alertmanager.yml                   ← шаблон routing+email (с ${VAR}, рендерится в runtime)
│   └── render-alertmanager.sh             ← entrypoint: рендер ${VAR} → /tmp/alertmanager.yml (Go не интерполирует env)
├── grafana/
│   ├── portal-overview.json               ← дашборд метрик (RED + audit + worker)
│   ├── portal-logs.json                   ← дашборд логов (ошибки, объём, request_id)
│   ├── portal-infrastructure.json         ← PostgreSQL, Redis, Host, Nginx (из exporter'ов)
│   ├── portal-storage.json                ← объёмы хранилища (БД, папки /data, логи, volumes)
│   └── provisioning/
│       ├── datasources/
│       │   ├── prometheus.yml             ← auto-provision Prometheus (uid=prometheus)
│       │   └── loki.yml                   ← auto-provision Loki (uid=loki)
│       └── dashboards/portal.yml          ← auto-provision дашбордов из JSON
├── node-exporter-textfile/                ← sidecar для textfile-collector (см. ниже)
│   ├── Dockerfile                         ← alpine + jq + tini + crond
│   ├── collect.sh                         ← du по папкам /data/* и Docker json-file логам
│   └── crontab                            ← расписание (каждые 5 мин)
├── textfile/                              ← общий rw-volume: storage-collector пишет, node-exporter читает
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
| Grafana | `:3001` | Единый UI: метрики + логи. admin/admin (смена при первом входе) |
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

### storage-collector (sidecar для объёмов на диске)

node-exporter видит только целую файловую систему (не поддиректории), а
json-file логи Docker лежат в `/var/lib/docker/containers/*` — вне путей,
примонтированных к контейнерам портала. Чтобы дашборд **«Portal — Storage»**
показывал размеры отдельных папок (`/data/photos/originals`, `/data/kb`,
`base_data/postgres`, …) и объём логов каждого контейнера, добавлен лёгкий
sidecar `storage-collector`:

- **Образ:** `monitoring/node-exporter-textfile/` (alpine:3.20 + jq + tini,
  busybox crond). ~10 МБ RAM, не открывает портов.
- **Как работает:** каждые 5 мин `collect.sh` делает `du -sb` по папкам данных
  портала (`upload_data/*`, `base_data/*`, `system_data/*`) и суммирует размеры
  `*-json.log*` каждого контейнера (имя сервиса — из compose-label), результат
  атомарно пишется в `monitoring/textfile/storage.prom`.
- **node-exporter** отдаёт этот файл через `--collector.textfile.directory=/textfile`
  как метрики `portal_storage_folder_bytes`, `portal_storage_docker_logs_bytes`,
  `portal_storage_docker_volume_bytes`.
- **Путь портала на хосте** задаётся через env `PORTAL_HOST_PATH` (дефолт
  `/home/snow/portal`); все пути сбора внутри контейнера — `/host + <path>`,
  т.к. host-ФС примонтирована read-only в `/host`.

Loki теперь дополнительно скрейпится Prometheus (job `loki` в `prometheus.yml`),
чтобы дашборд показывал состояние хранилища логов (`loki_ingester_wal_bytes_in_use`,
`loki_ingester_chunk_stored_bytes_total`, и др.).

Пересборка после правок скрипта/расписания:
```bash
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  build storage-collector && \
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  up -d storage-collector node-exporter
```

Проверка, что метрики пришли:
```bash
# из node-exporter (после первого сбора, ≤5 мин):
curl -s localhost:9100/metrics | grep '^portal_storage_'

# из Prometheus:
curl -s -G localhost:9090/api/v1/query --data-urlencode 'query=portal_storage_folder_bytes{folder="upload_data/photos/originals"}'
```

### Дашборды Grafana

| Дашборд | UID | Покрытие |
|---|---|---|
| Portal — Overview | `portal-overview` | RED backend (rate/errors/latency), audit pipeline, ARQ-задачи (jobs/duration/failures), бизнес-метрики (SSE, активные юзеры, KB/news/photos), outbox-очереди, integration-probes, **synthetic-пробы** (end-to-end user-flow; см. `docs/monitoring.md` §3) |
| Portal — Logs | `portal-logs` | Ошибки, slow-nginx, 5xx, трассировка по `request_id` |
| Portal — Infrastructure | `portal-infra` | PostgreSQL, Redis, Host (диск/CPU/RAM), Nginx — метрики из exporter'ов |
| Portal — Storage | `portal-storage` | Объёмы: БД + топ таблиц, Redis, папки `/data/*` + `base_data/*`, Docker json-file логи per-container, Loki chunks/WAL, заполнение ФС, Prometheus TSDB vs лимит |

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

# Alertmanager (шаблон ${VAR} нужно сначала отрендерить — Go не интерполирует env):
# Вариант 1 — через наш render-скрипт (как делает контейнер при старте):
docker run --rm -v ./monitoring/alerts:/alerts:ro \
  -e ALERT_SMTP_HOST=localhost -e ALERT_SMTP_PORT=25 -e ALERT_SMTP_FROM=a@b \
  -e ALERT_SMTP_USER= -e ALERT_SMTP_PASSWORD= -e ALERT_ADMINS_EMAIL=c@d \
  --entrypoint /bin/sh prom/alertmanager:v0.27.0 \
  -c '/alerts/render-alertmanager.sh && \
      ALERTMANAGER_OUT=/tmp/alertmanager.yml exec amtool check-config /tmp/alertmanager.yml'
# (скрипт рендерит шаблон и exec'ает alertmanager; для чистой проверки уберите
#  exec и замените последней строкой на "amtool check-config /tmp/alertmanager.yml")
# Вариант 2 — если контейнер уже запущен, проверить отрендеренный конфиг:
docker exec portal-alertmanager amtool check-config /tmp/alertmanager.yml

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
