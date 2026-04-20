# Phase 0 — Инфраструктура

> Статус: ✅ Завершено (апрель 2026)
> Следующая фаза: [Phase 1 — Auth + Users + News](./phase-1.md)

---

## Что реализовано

### Структура репозитория

```
portal/
├── docker-compose.yml          ← все 6 сервисов
├── .env.example                ← все переменные с комментариями
├── postgres/
│   ├── Dockerfile              ← postgres:16 + hunspell-ru
│   └── hunspell/
│       └── russian.stop        ← стоп-слова для FTS
├── nginx/
│   ├── nginx.conf              ← TLS, security headers, IP-whitelist
│   └── certs/                  ← .gitkeep (TLS-сертификаты добавить вручную)
├── backend/
│   ├── Dockerfile              ← multi-stage + Playwright/Chromium
│   ├── pyproject.toml          ← все зависимости + ruff/mypy/pytest config
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py             ← FastAPI app + middlewares + Prometheus
│   │   ├── core/
│   │   │   ├── config.py       ← Pydantic Settings v2
│   │   │   ├── logging.py      ← structlog (JSON prod / Console dev)
│   │   │   └── database.py     ← SQLAlchemy async engine + session
│   │   ├── api/
│   │   │   └── health.py       ← GET /health, GET /ready
│   │   ├── models/
│   │   │   └── user.py         ← SQLAlchemy модель User
│   │   └── worker/
│   │       ├── main.py         ← ARQ WorkerSettings + cron jobs
│   │       └── tasks/
│   │           └── audit.py    ← flush_audit_queue, partition tasks
│   ├── migrations/
│   │   ├── init.sql            ← расширения PG + FTS + первые партиции
│   │   ├── env.py              ← Alembic async env
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_initial_users.py
│   ├── scripts/
│   │   └── create_audit_partitions.py
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_config.py
│       │   ├── test_health.py
│       │   └── test_audit_partitions.py
│       └── integration/
│           └── test_migrations.py
├── frontend/
│   ├── Dockerfile              ← node:22 build → nginx:1.27 serve
│   ├── package.json            ← Vue 3, Naive UI, TipTap v2, vue-i18n v9, ...
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── nginx.spa.conf          ← SPA fallback + static caching
│   ├── scripts/
│   │   └── check-i18n.js       ← CI: паритет ключей ru↔en
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── router.ts
│       ├── stores/theme.ts
│       ├── i18n/ru.json + en.json
│       └── pages/              ← HomePage, AuthCallbackPage, NotFoundPage
└── .github/workflows/
    ├── ci.yml                  ← lint + tests на каждый PR
    └── build.yml               ← сборка образов при merge в main
```

---

## Технические нюансы и решения

### PostgreSQL + hunspell_ru

**Проблема:** стандартный `postgres:16-alpine` не содержит hunspell-словари, нужные для FTS с лемматизацией.

**Решение:** используем `postgres:16` (Debian-base) вместо alpine.
```dockerfile
RUN apt-get install -y hunspell-ru \
    && cp /usr/share/hunspell/ru_RU.dic "$PGSHARE/tsearch_data/russian.dict" \
    && cp /usr/share/hunspell/ru_RU.aff "$PGSHARE/tsearch_data/russian.affix"
```
Файл `russian.stop` хранится в репозитории (`postgres/hunspell/russian.stop`) и копируется при сборке образа.

**Важно:** `init.sql` выполняется через `docker-entrypoint-initdb.d` **только при первом старте** контейнера (пустой volume). При пересоздании контейнера с существующим volume — не выполняется повторно.

### Audit Log: партиционирование

Таблица `audit_log` партиционирована по `created_at` (native PG16, без pg_partman). Партиции создаются двумя механизмами:
1. **`init.sql`** — DO-блок создаёт 3 партиции при первом старте (текущий + 2 следующих месяца)
2. **ARQ cron** — `create_next_audit_partition` 1-го числа каждого месяца в 02:00 создаёт партиции на 2 месяца вперёд
3. **CLI** — `python -m scripts.create_audit_partitions` — при ручном деплое или восстановлении

**Запись в audit_log** — fire-and-forget: `BackgroundTasks` → Redis list `audit_queue` → ARQ worker batch INSERT каждые 2 секунды (`LMPOP 500`).

### Nginx: IP-whitelist

В `nginx.conf` используется `geo $allowed_network` с хардкоденными CIDR `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`. При деплое в среду с другими диапазонами — заменить вручную или через `envsubst` в `docker-compose.yml` command.

### Backend: Playwright в production-образе

`backend/Dockerfile` устанавливает Playwright/Chromium в финальном production-образе, так как он используется для PDF-экспорта статей. Это ~300 МБ дополнительного размера образа — принятое решение (см. ADR).

### Alembic: async engine

`migrations/env.py` использует `async_engine_from_config` — это нестандартный Alembic-паттерн. При проблемах с миграцией убедиться что `asyncpg` установлен и `DATABASE_URL` использует `postgresql+asyncpg://` драйвер.

### ARQ Worker: cron vs functions

В `worker/main.py` в `WorkerSettings.functions` пока пустой список. Функции, которые вызываются через `.enqueue_job()`, добавляются в Phase 1+. Cron-задачи (audit) работают независимо.

### Frontend: i18n паритет

Скрипт `frontend/scripts/check-i18n.js` запускается в CI (`npm run i18n:check`). Если в `en.json` отсутствуют ключи из `ru.json` — CI падает. Это гарантирует что при добавлении нового русского текста разработчик **обязан** добавить английский перевод.

---

## Зависимости между компонентами

```
postgres (healthcheck: pg_isready)
    ↓
backend (healthcheck: /ready → DB+Redis)
    ↓
nginx (depends: backend + frontend)

redis (healthcheck: redis-cli ping)
    ↓
backend
    ↓
worker (depends: backend healthcheck)
```

**Важно:** `worker` использует тот же Docker-образ что и `backend` (`portal-backend:latest`). Разница только в команде запуска: backend — `uvicorn`, worker — `python -m arq`.

---

## Переменные окружения (обязательные)

| Переменная | Описание |
|-----------|---------|
| `POSTGRES_PASSWORD` | пароль PostgreSQL (нет default) |
| `REDIS_PASSWORD` | пароль Redis (нет default) |
| `SECRET_KEY` | ≥32 символа, используется для CSRF/sessions |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://:password@redis:6379/0` |
| `KEYCLOAK_URL` | базовый URL Keycloak |
| `KEYCLOAK_CLIENT_SECRET` | секрет OIDC-клиента |

Все остальные — в `.env.example` с defaults.

---

## Запуск локально (dev)

```bash
cp .env.example .env
# Заполнить обязательные переменные в .env

docker compose up postgres redis -d
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

---

## Покрытие тестами Phase 0

| Файл | Тип | Кейсов | Покрытие |
|------|-----|--------|---------|
| `tests/unit/test_config.py` | unit | 7 | Валидация Settings, defaults, edge cases |
| `tests/unit/test_health.py` | unit | 6 | Liveness 200, readiness OK/DB-fail/Redis-fail/both-fail |
| `tests/unit/test_audit_partitions.py` | unit | 9 | Naming, create/skip, date ranges, drop retention |
| `tests/integration/test_migrations.py` | integration | 7 | upgrade→verify columns/indexes→downgrade→upgrade again |

**Запуск:**
```bash
cd backend
pytest tests/unit -v                    # быстро (~2 сек)
pytest tests/integration -v             # медленно (~20 сек, Docker required)
pytest --cov=app --cov-report=term      # с покрытием
```
