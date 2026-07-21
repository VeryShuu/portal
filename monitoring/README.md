# Observability stack — reference configs

Reference конфигурация Prometheus + Alertmanager + Grafana для портала.
**Не** подключена к основному `docker-compose.yml` — поднимается отдельным
overlay, чтобы не тащить тяжёлые образы в базовый деплой.

> **Подробности:** `../docs/monitoring.md` (backend-экспорт метрик, токен-защита
> `/metrics`, cross-process snapshot). Этот каталог — **consumer-сторона**:
> scrape-конфиг, alerting-правила, дашборд.

## Структура

```
monitoring/
├── README.md                          ← этот файл
├── prometheus.yml                     ← scrape-конфиг (portal-backend + self)
├── alerts/
│   ├── portal.yml                     ← alerting rules (PromQL)
│   └── alertmanager.yml               ← routing (webhook/email placeholders)
├── grafana/
│   ├── portal-overview.json           ← дашборд (RED + audit queue + worker)
│   └── provisioning/
│       ├── datasources/prometheus.yml ← auto-provision Prometheus datasource
│       └── dashboards/portal.yml      ← auto-provision dashboard из JSON
└── docker-compose.monitoring.yml      ← overlay для `docker compose -f ...`
```

## Запуск (overlay)

```bash
docker compose \
  -f docker-compose.yml \
  -f monitoring/docker-compose.monitoring.yml \
  up -d prometheus alertmanager grafana
```

Сервисы подключаются к сети `portal_internal` (см. основной `docker-compose.yml`),
поэтому видят `backend` и друг друга. `/metrics` портала скрапится как
`http://backend:8000/metrics`.

## Настройка scrape-токена

Backend защищает `/metrics` заголовком `X-Metrics-Token` (см. `docs/monitoring.md`
§3, `middleware/metrics.py::_require_metrics_token`). Если токен задан в
`/data/settings/system.json::metrics_token`, прописываем его в
`prometheus.yml::authorization.credentials` (или `bearer_token`). **Не
коммитить реальный токен в git** — использовать env-переменную:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "portal"
    scheme: http
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials: ${PORTAL_METRICS_TOKEN}  # пусто = /metrics открыт (закрытый периметр)
    static_configs:
      - targets: ["backend:8000"]
```

Запуск с токеном:

```bash
PORTAL_METRICS_TOKEN="$(jq -r .metrics_token // empty /data/settings/system.json)" \
  docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d prometheus
```

## Проверка конфигов

```bash
# Prometheus (нужен установленный promtool, либо через docker):
docker compose -f monitoring/docker-compose.monitoring.yml run --rm prometheus \
  promtool check config /etc/prometheus/prometheus.yml

# Alertmanager:
docker compose -f monitoring/docker-compose.monitoring.yml run --rm alertmanager \
  amtool check-config /etc/alertmanager/alertmanager.yml

# Alert rules (PromQL-синтаксис):
docker compose -f monitoring/docker-compose.monitoring.yml run --rm prometheus \
  promtool check rules /etc/prometheus/rules/portal.yml
```

## Грабли

- **Cross-process snapshot:** гейджи `portal_audit_queue_depth`,
  `portal_audit_processing_depth`, `portal_active_users_last_1h` и т.п.
  обновляются ARQ-cron'ом `refresh_custom_metrics` раз в 30с → пишутся в Redis
  `metrics:snapshot` → подтягиваются в API-process при scrape. Лаг ≤30с —
  поэтому все алерты на эти гейджи имеют `for: 5m` минимум.
- **Гейджи без воркера "замерзают".** Если `portal-worker` не запущен,
  `metrics:snapshot` не обновляется → кастомные метрики показывают
  устаревшие значения. Алерт `PortalWorkerDown` поймает это по отсутствию
  `arq:heartbeat` (TTL 90с в Redis, обновляется cron'ом каждые 30с).
- **`/health` и `/ready` исключены** из RED-метрик (см. `middleware/metrics.py`),
  поэтому в Prometheus их не видно — это нормально, они для оркестратора.
- **`alertmanager.yml` — заглушка.** Реальные receivers (email/Slack/Telegram)
  настраивает команда под свою инфраструктуру. Шаблон в `alerts/alertmanager.yml`
  показывает структуру.
- **Grafana provisions без пароля** (admin/admin при первом старте — сменить!).
  Для закрытого периметра допустимо; для публичного деплоя — настроить OAuth
  или reverse-proxy auth.
