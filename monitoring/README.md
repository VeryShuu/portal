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
├── prometheus.yml                         ← scrape-конфиг (backend + self + loki; ${VAR}-шаблон)
├── prometheus/
│   └── render-prometheus.sh               ← entrypoint: рендер ${VAR} (токен) → /tmp/prometheus.yml
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

UI (адрес привязки задаётся `MONITORING_BIND` в `.env` — по умолчанию
`127.0.0.1`, т.е. доступ только с хоста через SSH-туннель или reverse-proxy).
Исключение — Grafana: у неё собственная авторизация, поэтому она привязана
отдельной переменной `GRAFANA_BIND` (дефолт `0.0.0.0` — доступна из сети на
`:3001`; `127.0.0.1` — заблокировать, как остальные UI):

| Сервис | Порт | Назначение |
|---|---|---|
| Grafana | `:3001` | Единый UI: метрики + логи, доступен из сети (`GRAFANA_BIND`, дефолт `0.0.0.0`). Логин из `.env` (`GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD`, действует на свежем volume). Абсолютные ссылки — `GRAFANA_ROOT_URL` |
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
| redis-exporter | `:9121` | `oliver006/redis_exporter:v1.89.0` | Память/evictions, клиенты, keyspace hit rate |
| node-exporter | `:9100` | `prom/node-exporter:v1.12.1` | Диск (критично — `/data/photos`), CPU, RAM, load |
| nginx-exporter | `:9113` | `nginx/nginx-prometheus-exporter:1.5.3` | Active connections, request rate (через `stub_status`) |
| cadvisor | `:8081` | `gcr.io/cadvisor/cadvisor:v0.55.1` | Per-container CPU/RAM/IO + `container_start_time` (рестарт-лупы; OOM-kill детектится косвенно). Шумные `container_label_*` вырезаются `metric_relabel_configs` |
| blackbox-exporter | `:9115` | `prometheuscommunity/blackbox-exporter:v0.28.0` | Внешние HTTP(S)-пробы (DNS→TLS→nginx) + срок TLS-сертификатов. Цели — `BLACKBOX_TARGETS`/`BLACKBOX_TARGETS_INSECURE` в `.env` (file_sd) |

Nginx отдаёт `stub_status` на `http://nginx:8080/stub_status` (только из сети
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
  `*-json.log*` каждого контейнера, результат атомарно пишется в
  `monitoring/textfile/storage.prom`. Лейблы `container` (уникальное имя
  контейнера), `project`, `service` (compose-лейблы) — два проекта/реплики
  дают различные ряды (MON-12). Ошибки сбора различаются от пустых папок:
  `portal_storage_collector_error{reason="root_missing"}`,
  `portal_storage_collector_read_errors`; `last_run_seconds` обновляет только
  успешный прогон.
- **node-exporter** отдаёт этот файл через `--collector.textfile.directory=/textfile`
  как метрики `portal_storage_folder_bytes`, `portal_storage_docker_logs_bytes`,
  `portal_storage_docker_volume_bytes`.
- **Путь портала на хосте** задаётся через env `PORTAL_HOST_PATH` (дефолт
  `/home/snow/portal`); все пути сбора внутри контейнера — `/host + <path>`,
  т.к. host-ФС примонтирована read-only в `/host`.

Loki теперь дополнительно скрейпится Prometheus (job `loki` в `prometheus.yml`),
чтобы дашборд показывал состояние хранилища логов (`loki_ingester_wal_bytes_in_use`,
`loki_ingester_chunk_stored_bytes_total`, и др.).

Обновление после правок скрипта/расписания:

```bash
# dev-контур (IMAGE_PREFIX пуст): локальная пересборка
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  build storage-collector && \
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  up -d storage-collector node-exporter
```

**prod-контур (MON-19):** образ `portal-storage-collector` публикуется CI'ем в
Forgejo Registry (forgejo.mage.ru/mage/portal-storage-collector, теги как у
остальных: sha-<sha> / latest / semver) — обновление сводится к
`IMAGE_TAG=<версия>` в .env и `docker compose pull`. Локальная сборка на проде
заблокирована профилем (ADR-045/046).

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
| Portal — Overview | `portal-overview` | RED backend (rate/errors/latency), audit pipeline, ARQ-задачи (jobs/duration/failures), бизнес-метрики (SSE, активные юзеры, KB/news/photos), outbox-очереди, integration-probes, **synthetic-пробы** (внутренний local-auth → Home/bootstrap; см. `docs/monitoring.md` §3) |
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

> **Рендер при старте.** Prometheus не умеет раскрывать `${VAR}` в конфиге —
> подстановку делает entrypoint-скрипт `prometheus/render-prometheus.sh`
> (по образцу `render-alertmanager.sh`): подставляет токен, при пустом
> значении вырезает `authorization`-блок целиком, проверяет результат
> `promtool check config` и exec'ает Prometheus. До этого (до 2026-08) токен
> оставался литеральной строкой `${PORTAL_METRICS_TOKEN}` — при заданном
> токене scrape падал в 403.

Пустой токен → `/metrics` открыт (допустимо в закрытом периметре/VPN).

## Email-доставка алертов

`alertmanager.yml` шлёт алерты админам через **прямой SMTP-relay** (env-параметризуемые
`${ALERT_SMTP_*}`), независимый от portal `email_outbox` — критично: алерты уходят
даже при падении backend/worker. Переменные задаются в `.env` (см. `.env.example`,
секция Observability). При пустом `ALERT_SMTP_HOST` алерты видны только в UI Alertmanager.

### Дубль алертов в Matrix (опционально)

Мгновенный канал дублем к email: bridge `matrix-alertmanager`
(jaywink/matrix-alertmanager, compose-профиль `matrix`) принимает webhook
Alertmanager и постит в комнату админов. Включение:

1. В `.env` заполнить `ALERT_MATRIX_*` (homeserver, бот — можно существующий
   `@portal-bot`, токен, `ALERT_MATRIX_ROOMS=admins-email/!ROOM_ID:...`,
   `ALERT_MATRIX_WEBHOOK_URL`).
2. Поднять bridge: `COMPOSE_PROFILES=matrix docker compose ... up -d matrix-alertmanager`.
3. Рестарт `alertmanager` — render-скрипт добавит `webhook_configs` (при пустом
   `ALERT_MATRIX_WEBHOOK_URL` блок вырезается, email — единственный канал).

Bridge отдельный от portal `messenger_outbox` намеренно (как и прямой SMTP):
алерты обязаны доходить при упавшем портале. Email остаётся резервным каналом.

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

# Prometheus (шаблон ${VAR} рендерится — как в контейнере, через наш скрипт;
# он же гоняет promtool check config и печатает результат):
docker run --rm \
  -v ./monitoring/prometheus.yml:/etc/prometheus/prometheus.tmpl:ro \
  -v ./monitoring/prometheus/render-prometheus.sh:/usr/local/bin/render-prometheus.sh:ro \
  -v ./monitoring/alerts/portal.yml:/etc/prometheus/rules/portal.yml:ro \
  -e PORTAL_METRICS_TOKEN= \
  --entrypoint /bin/sh prom/prometheus:v3.13.2 \
  -c 'PROMETHEUS_OUT=/tmp/p.yml /usr/local/bin/render-prometheus.sh --version >/dev/null; \
      promtool check config /tmp/p.yml'
# (передайте -e PORTAL_METRICS_TOKEN=<значение> для проверки моды с токеном;
#  в запущенном контейнере: docker exec portal-prometheus promtool check config /tmp/prometheus.yml)

# Alert rules (PromQL-синтаксис):
docker compose -f monitoring/docker-compose.monitoring.yml run --rm prometheus \
  promtool check rules /etc/prometheus/rules/portal.yml

# Alertmanager (шаблон ${VAR} нужно сначала отрендерить — Go не интерполирует env):
# Вариант 1 — через наш render-скрипт (как делает контейнер при старте):
docker run --rm -v ./monitoring/alerts:/alerts:ro \
  -e ALERT_SMTP_HOST=localhost -e ALERT_SMTP_PORT=25 -e ALERT_SMTP_FROM=a@b \
  -e ALERT_SMTP_USER= -e ALERT_SMTP_PASSWORD= -e ALERT_ADMINS_EMAIL=c@d \
  --entrypoint /bin/sh prom/alertmanager:v0.33.1 \
  -c '/alerts/render-alertmanager.sh && \
      ALERTMANAGER_OUT=/tmp/alertmanager.yml exec amtool check-config /tmp/alertmanager.yml'
# (скрипт рендерит шаблон и exec'ает alertmanager; для чистой проверки уберите
#  exec и замените последней строкой на "amtool check-config /tmp/alertmanager.yml")
# Вариант 2 — если контейнер уже запущен, проверить отрендеренный конфиг:
docker exec portal-alertmanager amtool check-config /tmp/alertmanager.yml

# Alloy (River-синтаксис):
docker run --rm -v ./monitoring/alloy/config.alloy:/etc/alloy/config.alloy:ro \
  --entrypoint alloy grafana/alloy:v1.18.1 fmt --test /etc/alloy/config.alloy
```

## Грабли

- **Single-file bind mounts (rules) отслеживают inode.** portal.yml/recording.yml
  монтируются в prometheus как отдельные файлы: правка в репо создаёт НОВЫЙ
  inode, а контейнер продолжает видеть старый — даже после `POST /-/reload`.
  После правки rules: `docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d --force-recreate prometheus`.
- **Pattern ingester (Loki)** — отдельный target, в дефолтный `all` не входит:
  в compose включён флагом `-target=all,pattern-ingester`. Patterns строятся
  только по логам, принятым ПОСЛЕ включения (ретроактивно — нет). UI:
  Grafana → Drilldown → Logs (плагин `grafana-lokiexplore-app`, включается
  `GRAFANA_INSTALL_PLUGINS` в .env — нужен доступ к grafana.com).
- **Recording rules** (`alerts/recording.yml`) — предагрегация RED/SLO для
  дашбордов (`portal:http_*`, `portal:slo_availability_5m`); алерты остаются
  на сырых метриках (своя семантика и пороги).

- **Loki 3.6+ и Alloy не содержат `wget`/`curl`** (busybox убран, upstream
  issues grafana/loki#20149, grafana/alloy#477). Встроенный HTTP-healthcheck
  невозможен — убран. Готовность: `restart` + ручная проверка с хоста.
- **Cross-process snapshot:** гейджи `portal_audit_queue_depth`,
  `portal_audit_processing_depth`, `portal_active_users_last_1h` обновляются
  ARQ-cron'ом `refresh_custom_metrics` раз в 30с → пишутся в Redis
  `metrics:snapshot` → подтягиваются в API-process при scrape.
  `portal_metrics_snapshot_generated_timestamp_seconds` фиксирует завершение
  сбора, а `portal_metrics_snapshot_read_success` — успех чтения и гидратации
  на текущем scrape.
- **Integration probe state:** постоянный `integration:probe:state` хранит
  expected/last_attempt/last_completed и срок валидности результата. Карточки
  Overview различают `DISABLED / STALE / DOWN / UP`, а
  `PortalIntegrationProbeStale` ловит expected probe без свежего завершения.
  Collabora считается UP только после авторизованного OCS capabilities Nextcloud
  и прямого ответа настроенного `/hosting/capabilities` с `productVersion`;
  302/404 и login HTML дают DOWN.
- **Synthetic probe state:** screenshot-service напрямую отдаёт приватный
  `/metrics`; только этот процесс знает `PROBE_ADMIN_*` и публикует expected,
  last_attempt, last_completed, result_available, up и duration. Prometheus job
  `screenshot-service` различает DISABLED/STALE/DOWN/UP и отдельно тревожит при
  недоступности самого target. Flow проверяет HomePage marker, совпадающего
  local user в `/api/v1/bootstrap` и отсутствие `pageerror`; он не покрывает
  SSO и внешний TLS. Результат свеж 15 минут; restart не сохраняет прежний
  зелёный статус.

- **Гейджи без воркера «замерзают».** Старые значения могут остаться в памяти
  API, поэтому `PortalMetricsSnapshotStale` отдельно тревожит при неуспешном
  чтении снапшота или возрасте публикации >120с. `PortalWorkerDown` независимо
  контролирует heartbeat самого worker.
- **`request_id` — НЕ Loki-лейбл** (high-cardinality). Лейблы только `service`,
  `level`, `container`, `compose_service`. Поиск request_id через LogQL `| json`.
- **`/health` и `/ready` исключены** из RED-метрик (см. `middleware/metrics.py`),
  поэтому в Prometheus их не видно — это нормально, они для оркестратора.
- **Фиксированные UID datasource** (`uid: loki`, `uid: prometheus`) обязательны —
  без них Grafana генерирует случайные UID, дашборды не находят datasource'ы.
- **Prometheus 3.x (обновление 2026-08 с 2.54):** TSDB-данные 2.x читаются 3.x
  без конвертации, но обратный откат после работы 3.x на старом volume не
  гарантируется (migration guide) — перед откатом бэкапить `prometheus-data`.
  3.x строго проверяет Content-Type при scrape (2.x молча фолбэчился в text
  format) — все наши цели (backend + exporter'ы) отдают корректные заголовки.
- **Grafana 13 (обновление 2026-08 с 11.2):** дашборды/provisioning-схема
  совместимы (React-панели, валидные UID). Перед обновлением на проде иметь
  запас места на volume `grafana-data` (миграция annotation-таблицы v11→v12
  делает full-rewrite); дашборды у нас provisioned из git — потеря БД Grafana
  некритична (восстановятся при старте).
