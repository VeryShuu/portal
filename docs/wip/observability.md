# Фича: Observability-стек (Grafana + Loki + Prometheus + Alloy) + удаление Sentry

> **Когда читать:** возобновляешь работу по observability-стеку портала
> (логирование/метрики/alerting) — этот план хранит контекст между сессиями.
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> **Связанный план:** `observability-remediation.md` — завершённая сессия 1
> (2026-07-21): Prometheus + Alertmanager + Grafana reference, alert-rules,
> дашборд portal-overview. Этот план продолжает работу (сессии 2–3).
> **ADR:** ADR-044 (обоснование выбора Loki/Alloy, overlay-подхода).

## Цель

Дать единую точку наблюдаемости за порталом: централизованный просмотр логов
и метрик в Grafana, alerting на системные проблемы (5xx, рост очереди аудита,
падение воркера), всё offline-capable для интранет/VPN. И полностью вычистить
Sentry (не используется, не планируется).

## Решения по ходу

- **2026-07-21** (сессия 1, см. `observability-remediation.md`): observability-стек
  оформлен как **reference-конфиги в `monitoring/`** — БЕЗ правок основного
  `docker-compose.yml`. Поднимается overlay. Причина: не ломать prod-деплой,
  не тащить тяжёлые образы в базовый compose.
- **2026-07-22** (сессия 1 этой фичи): **полное удаление Sentry** (не оживление).
  Пользователь не использует и не планирует. Вычищено из кода/тестов/UI/док/
  openapi/инфры. Ошибки теперь через structlog `logger.exception(...)` → Loki.
- **2026-07-22** (сессия 1): **мёртвые ARQ-счётчики удалены**, не оживлены.
  `portal_arq_jobs_enqueued_total` / `_failed_total` объявлены, но нигде не
  инкрементировались. ARQ 0.26 не передаёт флаг успеха в `on_job_end`
  (`success` — локальная переменная внутри `run_job`). Чистого способа
  инкремента нет → удалены (по принципу «никаких костылей»). Состояние воркера
  ловит `PortalWorkerStale` (по heartbeat/gauge). Алерт `PortalArqJobsFailing`
  удалён.
- **2026-07-22** (сессия 2): **Loki выбран вместо ELK/Graylog** — Loki индексирует
  только лейблы (не текст), ~400 МБ RAM, structlog-JSON уже совместим. ELK
  прожорлив (~3–4 ГБ), Elastic License 2.0, оверкилл для ~300 юзеров.
- **2026-07-22** (сессия 2): **Alloy вместо Promtail** — Promtail в maintenance,
  Alloy текущий активный проект Grafana. `loki.source.docker` через Docker
  socket discovery — канонический паттерн (attach к stdout/stderr).
- **2026-07-22** (сессия 2): **email-доставка через прямой SMTP-relay**, не через
  portal `email_outbox`. Причина: Alertmanager должен уведомить даже при падении
  backend/worker — независимый путь критичен. Параметризуется env
  (`${ALERT_SMTP_*}`). При пустом `ALERT_SMTP_HOST` — алерты только в UI.
- **2026-07-22** (сессия 2): **healthcheck убран у Loki/Alloy** — образы 3.6+ и
  Alloy не содержат wget/curl (busybox убран, upstream issues #20149, #477).
  Честнее, чем плодить кастомные образы ради одной проверки. Готовность через
  `restart: unless-stopped` + ручная проверка с хоста.

## Чеклист (DoD)

### Сессия 1 — вычистка Sentry + мёртвые счётчики (✅ готово)
- [x] Удалён `backend/app/core/sentry.py` + `tests/unit/test_sentry.py`
- [x] Вычищены импорты/вызовы из main, lifespan, _settings, audit, nc_federation
- [x] `sentry_dsn` убран из SystemSettings/In/Patch/Out + _loader + legacy-map
- [x] `sentry-sdk[fastapi]` убран из `pyproject.toml`
- [x] Frontend: MonitoringTab.vue, queries/admin.ts, 10 i18n-ключей ru/en
- [x] openapi.json + generated-доки перегенерированы
- [x] SENTRY_ENVIRONMENT убран из setup.sh + staging compose
- [x] Prose-правки в доках (monitoring.md, AGENTS.md, README, deploy, adr, audit)
- [x] Удалены мёртвые счётчики arq_jobs_enqueued/failed + алерт PortalArqJobsFailing
- [x] DoD: ruff ✓, mypy ✓ (352), pytest ✓ (3732), frontend lint/typecheck/i18n/test ✓

### Сессия 2 — Loki + Alloy + email-alerting (✅ готово)
- [x] `monitoring/loki/config.yml` — single-binary, retention 30d, compactor
- [x] `monitoring/alloy/config.alloy` — docker discovery + JSON-парсинг (валидирован)
- [x] Grafana datasource Loki (`uid: loki`) + prometheus (`uid: prometheus`)
- [x] `monitoring/grafana/portal-logs.json` — дашборд (7 панелей)
- [x] Overlay расширен: + loki, alloy, volume, env alertmanager
- [x] Фикс бага: mount `alerts/` → prometheus `rules/` ломал Prometheus
- [x] `alertmanager.yml` — email-receivers через SMTP-relay (amtool SUCCESS)
- [x] setup.sh + .env.example — секция Observability
- [x] Smoke-тест: 5 сервисов, scrape UP, дашборды провижн, логи текут, request_id корреляция

### Сессия 3 — документация (эта сессия)
- [x] ADR-044 в `docs/adr.md` (+ индекс ADR-043/044 + шапка)
- [x] Этот wip-план (`docs/wip/observability.md`)
- [ ] `docs/monitoring.md` §9 — централизованные логи (Loki + Alloy)
- [ ] `monitoring/README.md` — обновить под полный стек (5 сервисов)
- [ ] `docs/README.md` — роутер/ссылки под Loki
- [ ] DoD: доки консистентны, нет битых ссылок

## Грабли / контекст

- **Loki 3.6+ / Alloy не содержат wget/curl** (busybox убран). Healthcheck через
  HTTP сделать нечем — убран. Готовность: restart + ручная проверка с хоста
  (`curl http://localhost:3100/ready` для Loki, `http://localhost:12345/-/ready` для Alloy).
- **`${VAR:default}` НЕ работает в alertmanager.yml** — только `${VAR}` без дефолта.
  Дефолты задаются в overlay compose (`${ALERT_SMTP_HOST:-}`).
- **Фиксированные UID datasource обязательны** (`uid: loki`, `uid: prometheus`) —
  иначе Grafana генерирует случайные UID, дашборды не находят datasource'ы.
- **Alloy `loki.write.endpoint` без batchwait/batchsize** — это Promtail-атрибуты.
- **Mount `alerts/` в prometheus `rules/` ломает Prometheus** — он парсит
  alertmanager.yml как rules-файл и падает. Развели на файловый mount `portal.yml`.
- **`single_binary` поле удалено в Loki 3.x** — было в 2.x, теперь режим по умолчанию.
- **`request_id` — НЕ Loki-лейбл** (high-cardinality). Лейблы только `service`,
  `level`, `container`, `compose_service`. Поиск request_id через LogQL `| json`.
- **Docker socket для Alloy**: `/var/run/docker.sock:ro` — discovery + attach
  работают на чтение. Alloy не управляет контейнерами (не start/stop).
- **Алёртинг на gauge'и с cross-process snapshot**: лаг ≤30с (cron
  `refresh_custom_metrics`), поэтому все алерты имеют `for: ≥2–5m`.
- **`observability-remediation.md`** — исторический план завершённой сессии 1
  (2026-07-21). Содержит устаревшие упоминания Sentry (в handoff-записи) —
  это «дневник», удаляется целиком при мёрже этой фичи.

## Handoff

```
СДЕЛАНО:
  Сессия 1 (2026-07-22): Sentry полностью вычищен (~18 файлов: код/тесты/UI/
    openapi/инфра/доки). Мёртвые ARQ-счётчики + алерт PortalArqJobsFailing
    удалены. Backend ruff/mypy/pytest ✓ (3732 passed), frontend ✓ (2130).
    Пользователь закоммитил, образы пересобраны.
  Сессия 2 (2026-07-22): Loki 3.7.3 + Alloy 1.18.0 + дашборд portal-logs +
    email-alerting (alertmanager.yml через SMTP-relay). Overlay расширен,
    фикс бага mount alerts/→rules/. Smoke-тест: 5 сервисов UP, scrape OK,
    логи текут, JSON парсится, request_id корреляция работает, Grafana
    автозагружает 2 datasource + 2 дашборда. Пользователь закоммитит.
  Сессия 3 (эта): ADR-044 + индекс adr.md. Этот wip-план.

В РАБОТЕ: docs/monitoring.md §9 (централизованные логи), monitoring/README.md.

ДАЛЕЕ:
  1. docs/monitoring.md §9 — архитектура Loki+Alloy, LogQL-примеры, retention,
     грабли (high-cardinality request_id — НЕ лейбл).
  2. monitoring/README.md — обновить структуру под 5 сервисов + команду запуска
     + LogQL-примеры.
  3. docs/README.md — роутер «Health-пробы/метрики/логи → monitoring.md».
  4. Удалить docs/wip/observability-remediation.md при завершении фичи
     (исторический план сессии 1, содержит устаревшие Sentry-упоминания).

ОТКРЫТЫЕ ВОПРОСЫ:
  - Alertmanager receivers: email-доставка через прямой SMTP-relay (env).
    MAX-бот для алертов — отложено (webhook-placeholder убран, при желании
    добавить email_configs параллельно или отдельный webhook-приёмник).
  - Трейсинг (Tempo) — за рамками; архитектурно готов (Grafana), отдельный overlay.

КОММИТ: см. ниже (готов для сессии 3).
```
