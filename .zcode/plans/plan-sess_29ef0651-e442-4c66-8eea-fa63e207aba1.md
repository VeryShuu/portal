# План: Observability-стек (Grafana + Loki + Prometheus + Alloy) + вычистить Sentry

## Контекст находки (важно!)

В ходе разведки выяснилось, что **observability-стек уже частично построен** в прошлой сессии (21 июля 2026). В каталоге `monitoring/` уже есть:
- Prometheus (scrape `/metrics` + токен), 8 alert-правил, Alertmanager (stub).
- Grafana 11.2 + provisioning (datasource Prometheus, дашборд portal-overview с 14 панелями).
- Overlay `monitoring/docker-compose.monitoring.yml`.

Принятое архитектурное решение (`docs/wip/observability-remediation.md`): **reference-конфиги в `monitoring/`, БЕЗ правок основного `docker-compose.yml`**, поднимаются overlay-командой `docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml up -d ...`.

Поэтому задача = **не «с нуля», а**: (А) расширить overlay компонентами логирования (Loki + Alloy), (Б) вычистить Sentry под ноль, (В) активировать стек. Документирую как ADR-044 + продолжение wip-плана.

---

## Часть 1. Вычистить Sentry (полное удаление, ~18 файлов)

Решение пользователя: Sentry не используется и не планируется. Удаляем всё, без `@deprecated`-заглушек.

### Backend
- **Удалить целиком:** `backend/app/core/sentry.py`, `backend/tests/unit/test_sentry.py`.
- **`backend/app/main.py`** — убрать `import sentry_sdk` (L5), импорт `scrub_sensitive` (L14), блок `sentry_sdk.init(...)` (L32–40).
- **`backend/app/core/lifespan.py`** — убрать `import sentry_sdk` (L5) и два `sentry_sdk.capture_exception(...)` (L79, L95) вместе с `with suppress(Exception):`-обёртками; оставить `logger.warning(...)`.
- **`backend/app/api/system_settings/_settings.py`** — убрать импорт `scrub_sensitive` (L15), функцию `_reinit_sentry` (L42–54), ветку reinit (L74–75), `"sentry_dsn"` из audit-тупла секции observability (L125), строку `kwargs["sentry_dsn"] = ...` (L262), упоминание в docstring (L153).
- **`backend/app/core/system_config/_schemas.py`** — убрать `sentry_dsn` из `SystemSettings` (L110), `SystemSettingsIn` (L119–122), `SystemSettingsPatch` (L176–179), `sentry_dsn_set` из `SystemSettingsOut` (L226).
- **`backend/app/core/system_config/_loader.py`** — убрать `sentry_dsn_set=...` (L98) из `_to_out`.
- **`backend/app/core/system_config/_migrations.py`** — убрать `"SENTRY_DSN": "sentry_dsn"` (L25) из `_LEGACY_ENV_MAP`.
- **`backend/app/services/audit.py`** — убрать `import sentry_sdk` + `capture_exception` + debug-лог `audit.push_sentry_capture_failed` (L59–64); оставить `logger.exception("audit.push_failed", ...)`.
- **`backend/app/services/nc_federation.py`** — убрать `import sentry_sdk` (L53) и два вызова `capture_message`/`capture_exception` (L175–182); оставить `logger.warning(...)`.
- **`backend/pyproject.toml`** — убрать `"sentry-sdk[fastapi]>=2.3.0"` (L35).

### Тесты backend
- **`backend/tests/unit/test_system_settings.py`** — удалить `test_sentry_change_reinits_and_marks_observability` (L1110–1120), plumbing `sentry_init`/`sentry_stub` (L1061, 1071–1072, 1083, 1104), assertion `assert p.sentry_dsn is None` (L430).
- **`backend/tests/unit/test_config.py`** — убрать `"sentry_dsn"` из тупла ожидаемых legacy-полей (L162).
- **`backend/tests/unit/test_helpdesk_worker_locks.py`** — поправить prose-упоминание в docstring (L278).

### Frontend
- **`frontend/src/pages/admin/tabs/MonitoringTab.vue`** — удалить секцию Sentry (template L119–154), поля `sentry_dsn_set`/`sentry_dsn` из interface + form + watch + PATCH body (L199, 243, 257, 282, 285).
- **`frontend/src/queries/admin.ts`** — убрать `sentry_dsn_set: boolean` (L51).
- **`frontend/src/i18n/ru.json` + `en.json`** — убрать ключи `sentrySection/sentrySectionHint/sentryDsn/sentryDsnKeep/sentryDsnPlaceholder/sentryDsnHint` (2 места в каждом: L876–879, L953–958).
- **`frontend/src/api/types.gen.d.ts`** — перегенерировать (`npm run gen:types`), не править руками.

### OpenAPI / генерируемые доки
- **`openapi.json`** — убрать 4 блока `sentry_dsn`/`sentry_dsn_set` (L10979–10990, 11142–11145, 11168, 11486–11497). Перегенерить `docs/api-contracts.generated.md`, `docs/tests.generated.md`.

### Инфра
- **`docker-compose.staging.yml`** — убрать комментарий (L10) и `SENTRY_ENVIRONMENT: staging` (L35, L40).
- **`setup.sh`** — убрать в embedded staging-шаблоне (L516, L541, L546).

### Документация
- `AGENTS.md` (L191, 315, 357, 389), `README.md` (L89) — убрать упоминания Sentry из стека/дерева/списков.
- `docs/monitoring.md` — удалить §5 «Sentry» (L128–133), строку таблицы (L18, 21), упоминания (L151, 153, 242).
- `docs/deploy.md` (L92, L191), `docs/adr.md` (L1028, L1033), `docs/audit.md` (L110, 130, 169), `docs/README.md` (L25, 131), `docs/helpdesk.md` (L459), `docs/integration-keycloak-nextcloud.md` (L278, L314), `docs/wip/observability-remediation.md` (L31, 45, 179).
- `monitoring/alerts/portal.yml` (L58) — убрать «Смотреть Sentry» из runbook-описания алерта PortalHighErrorRate.

---

## Часть 2. Оживить мёртвые ARQ-счётчики (чистая доработка backend)

`portal_arq_jobs_enqueued_total` / `portal_arq_jobs_failed_total` объявлены, но нигде не инкрементируются → алерт `PortalArqJobsFailing` никогда не сработает, на дашборде нули.

- **`backend/app/core/metrics.py`** — без изменений (счётчики уже объявлены).
- **`backend/app/worker/main.py`** — в `on_job_end` (L158–159) добавить инкремент `portal_arq_jobs_failed_total.labels(function=...).inc()` при наличии исключения (ARQ передаёт `result`/исключение в контекст). В хелпере `enqueue_job`-обёртке (или в точках вызова `ctx['arq'].enqueue_job`) — инкремент `portal_arq_jobs_enqueued_total`. Точечное место уточню по коду в реализации.
- **Тест:** unit-тест на `on_job_end` с инжектированным исключением → счётчик вырос. Обновить существующий test, если есть покрытие.
- Проверить: `ruff check . && mypy app && pytest tests/unit`.

---

## Часть 3. Добавить Loki + Alloy в observability-overlay

### 3.1. Компоненты (4 новых сервиса в `monitoring/docker-compose.monitoring.yml`)

| Сервис | Образ | Сеть | Назначение |
|---|---|---|---|
| `loki` | `grafana/loki:3.2.1` | internal only | Хранилище логов, приём push от Alloy |
| `alloy` | `grafana/alloy:1.5.3` | internal + external | Сборщик: docker-container discovery → Loki; prometheus-metrics relay (опц.) |

**Логи без auth:** Loki-приёмник слушает на `:3100`, доступен только в `internal`-сети (как Prometheus). Grafana ходит к нему через datasource.

**Сеть Alloy:** `internal` (до всех контейнеров портала) + монтирование `/var/run/docker.sock` + `/var/lib/docker/containers` для чтения логов через discovery. Сеть `external` НЕ нужна (docker.sock доступен через bind-mount).

### 3.2. Конфиг Alloy (`monitoring/alloy/config.alloy`)

Discovery-режим: читает логи всех контейнеров проекта `portal` через Docker API (`discovery.docker` + `loki.source.docker`).

Парсинг:
- Контейнеры `portal-backend`/`portal-worker` — логи уже JSON от structlog → парсим как JSON, лейблы `service`, `level`, `request_id`, `job_id`, `logger` идут как Loki-лейблы (через `loki.process` → `json` stage). Лейбл `service` уже проставлен structlog-processor'ом (`portal-backend`/`portal-worker`).
- Контейнер `portal-nginx` — логи JSON (`json_combined` format из nginx.conf, уже есть поле `request_id`).
- Остальные (postgres/redis/...) — plain text, лейбл `container_name` через docker metadata.

Лейблинг-стратегия (минимум, по ADR-041): `container_name`, `service` (если есть), `level` (если есть). `request_id` — **НЕ** как лейбл (высокая кардинальность), а как parsed-поле для поиска в LogQL `{service="portal-backend"} | json | request_id="abc"`.

Relabel: дропаем служебные контейнеры observability-стека (portal-prometheus/grafana/loki/alloy), чтобы не было цикла.

### 3.3. Конфиг Loki (`monitoring/loki/config.yml`)

Single-binary режим (monolith, достаточно для ~300 юзеров):
- `auth_enabled: false` (внутренняя сеть).
- retention: `max_age: 30d` (как у Prometheus TSDB).
- compactor: включён, удаление по возрасту.
- limits: `reject_old_samples` (логи старше 7 дней не принимаем — защита от мусора при复读е), `ingestion_rate_mb: 8`, `max_streams_per_user` разумный.

Volume: `loki-data` (named, как prometheus-data/grafana-data).

### 3.4. Grafana datasource для Loki

Новый файл `monitoring/grafana/provisioning/datasources/loki.yml`:
```yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: false
    jsonData:
      maxLines: 1000
```
Существующий `prometheus.yml` datasource — без изменений.

### 3.5. Дашборд логов (`monitoring/grafana/portal-logs.json`)

Новый дашборд в папке Portal, панели:
1. **Error log stream** — `count_over_time({service=~"portal-backend|portal-worker", level=~"error|critical"}[5m])` — график + таблица последних 50 ошибок.
2. **Log volume by service** — `sum by (service)(count_over_time({service=~"portal-.*"}[5m]))`.
3. **Log volume by level** — `sum by (level)(count_over_time({service=~"portal-.*"}[5m]))`.
4. **Slow requests (nginx)** — `{container_name="portal-nginx"} | json | request_time > 2`.
5. **5xx errors (nginx)** — `{container_name="portal-nginx"} | json | status >= 500`.
6. **Explore-link по request_id** — пример LogQL: `{service="portal-backend"} | json | request_id="$__request_id"` (переменная из лога nginx).
7. **Audit-pipeline ошибки** — `{service="portal-worker", logger=~".*audit.*"}`.

Регистрация: добавить путь в `monitoring/grafana/provisioning/dashboards/portal.yml` (уже сканирует `/var/lib/grafana/dashboards`), примонтировать новый JSON в `docker-compose.monitoring.yml`.

### 3.6. Overlay-добавки в `docker-compose.monitoring.yml`

Добавить сервисы `loki`, `alloy` + volume `loki-data` + монтирования конфигов (`./monitoring/loki/config.yml`, `./monitoring/alloy/config.alloy`, `./monitoring/grafana/portal-logs.json`). Обновить header-комментарий про полный стек и команду запуска:
```bash
docker compose -f docker-compose.yml -f monitoring/docker-compose.monitoring.yml \
  up -d prometheus alertmanager grafana loki alloy
```

---

## Часть 4. Доставка алертов (решение по умолчанию: email админам)

Alertmanager-заглушку (`monitoring/alerts/alertmanager.yml`) наполняем реальным email-receiver через SMTP Postfix портала:
- `smtp_smarthost: "postfix:25"` (контейнер в internal-сети) — уточню имя сервиса по стеку.
- `to: admins@<домен>` — через env `PORTAL_ADMINS_EMAIL`.
- Routing как есть (critical → отдельная группа, warning → основная, info → drop).
- Webhook-placeholder комментарием оставляю как fallback для будущего MAX-бота.

Добавить `PORTAL_ADMINS_EMAIL` в `setup.sh::setup_env()` (через `ask()` с дефолтом).

> Email-доставка через outbox-паттерн портала (`email_outbox`) здесь **не применяется**: Alertmanager шлёт через свой SMTP-клиент напрямую в Postfix, это правильный путь (он независим от БД/outbox-воркера — если упал backend, алерт всё равно уйдёт).

---

## Часть 5. Активация + документация

### 5.1. ADR-044 (`docs/adr.md`)
Новый ADR (последний номер — 043). Заголовок: «ADR-044: Observability-стек — Grafana + Loki + Prometheus + Alloy, удаление Sentry». Секции по шаблону ADR-040/041 (Контекст / Решение с YAML-сниппетом / Альтернативы / Последствия). Зарегистрировать в индексе активных ADR (L18–55), обновить счётчик в шапке. Обосновать: почему Loki а не ELK (ресурсы, JSON-structlog уже совместим), почему Alloy а не Promtail (Alloy — текущий активный проект Grafana, Promtail в maintenance), почему overlay а не базовый compose (наследуем решение из wip-плана).

### 5.2. Wip-план (`docs/wip/observability.md`)
Новый файл по шаблону `_TEMPLATE.md` (старый `observability-remediation.md` — завершён, но не мёрджен; в новом плане дам ссылку на него как на источник решений Части 1 сессии). Чеклист DoD по этому плану.

### 5.3. `docs/monitoring.md` — обновить
- §1 таблица: строку «Ошибки | Sentry» → убрать (вместе с Частью 1); добавить описание Loki как «централизованные логи».
- §5 «Sentry» → удалить.
- §7 «Alerting и Grafana» → расширить: добавить Loki + Alloy в структуру `monitoring/`, команду запуска с полным стеком, новый logs-дашборд.
- Новый §9 «Централизованные логи (Loki + Alloy)»: архитектура сбора, лейбл-стратегия, LogQL-примеры, retention, грабли (high-cardinality `request_id` — НЕ лейбл).

### 5.4. `monitoring/README.md` — обновить
Структуру дерева + команду запуска полного стека (5 сервисов) + примеры LogQL-запросов.

### 5.5. `docs/README.md` — роутер
Строку «Health-пробы / метрики / логи / Sentry → monitoring.md» → «Health-пробы / метрики / логи → monitoring.md».

---

## Порядок выполнения (по сессиям)

**Сессия 1 (эта):** Часть 1 (Sentry-вычистка) — самая объёмная, но механическая. + Часть 2 (ARQ-счётчики, 2 строки + тест). DoD backend: `ruff check . && mypy app && pytest tests/unit` зелёные. DoD frontend: `npm run lint:check && typecheck && test:unit && i18n:check`.

**Сессия 2:** Часть 3 (Loki + Alloy конфиги + overlay) + Часть 4 (email-alerting). Валидация: `docker compose config --quiet`, локальный подъём стека, проверка что логи текут в Loki (`curl localhost:3000` → дашборд).

**Сессия 3:** Часть 5 (ADR-044, доки, wip-план, финальная проверка overlay на «боевом» стенде). Хэндофф.

## Definition of Done (общий)
- [ ] Sentry полностью вычищен (grep по репо = 0 осмысленных упоминаний, кроме git-истории).
- [ ] `sentry-sdk` убран из зависимостей, `pip install` не тянет его.
- [ ] Backend: `ruff check . && mypy app && pytest tests/unit` зелёные.
- [ ] Frontend: `npm run lint:check && typecheck && test:unit && i18n:check` зелёные.
- [ ] Overlay `docker compose config --quiet` валиден; `promtool check config` / `amtool check-config` проходят.
- [ ] Логи backend/worker/nginx видны в Loki (проверено локально).
- [ ] Метрики скрейпятся Prometheus (проверено: `up{job="portal"} == 1`).
- [ ] ADR-044 добавлен, индекс обновлён.
- [ ] `docs/monitoring.md` обновлён (Loki, удалён Sentry).
- [ ] Wip-план `docs/wip/observability.md` ведётся с handoff.

## Ресурсы (оценка поверх текущего compose)
- Loki: ~300–500 MB RAM, диск: объём зависит от трафика, retention 30d, compactor чистит.
- Alloy: ~100–150 MB RAM.
- Prometheus/Alertmanager/Grafana: уже учтены в существующем overlay.
- **Итого к overlay: +~500–650 MB RAM**, не трогает базовый compose.

## Не делаю (явные границы)
- НЕ меняю основной `docker-compose.yml` (наследую решение из wip-плана: overlay).
- НЕ меняю API-контракты по существу — только удаляю поле `sentry_dsn` (это removal, не semantic-change).
- НЕ добавляю Keycloak OIDC в Grafana (отдельная задача, если захочется SSO).
- НЕ перевожу x-logging anchor на loki-driver (наследую ADR-041: остаётся json-file, Alloy читает сверху) — меньше риск для prod.
- НЕ добавляю трейсинг (Tempo) — за рамками запроса; архитектурно готово (Grafana есть), добавляется отдельным overlay.
- НЕ настраиваю MAX-бот для алертов (email-достаточно; webhook-placeholder остаётся).