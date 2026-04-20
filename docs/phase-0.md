# Phase 0 — Инфраструктура

> Статус: ✅ Завершено (апрель 2026)
> Smoke-test `docker compose up -d --build`: все 6 контейнеров healthy/up
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

### Frontend: vue-tsc + Vite types

`tsconfig.json` содержит `skipLibCheck: true` и `types: ["vite/client", "node"]`. Без этих опций `vue-tsc --noEmit` падает на типах сторонних библиотек (Naive UI, TipTap) и на отсутствующем `import.meta.env`.

### Backend: structlog + stdlib LoggerFactory

В `app/core/logging.py` используется `structlog.stdlib.LoggerFactory()`, а **не** `PrintLoggerFactory()`. Причина — процессор `structlog.stdlib.add_logger_name` требует stdlib-логгер с атрибутом `.name`. С `PrintLogger` падает `AttributeError: 'PrintLogger' object has no attribute 'name'` на первом же `logger.info(...)`. `LoggerFactory()` также корректно интегрируется с uvicorn-логами через `ProcessorFormatter`.

### Nginx: CSP — одна строка

Директива `add_header Content-Security-Policy "..." always;` в `nginx.conf` записана **одной длинной строкой** с `always;` в конце. Многострочный синтаксис с переносом `always` на следующую строку приводит к `[emerg] invalid number of arguments in "add_header" directive` — nginx не склеивает токены между строками.

### Nginx: TLS-сертификаты обязательны для старта

Контейнер `portal-nginx` не запустится без файлов `nginx/certs/portal.crt` и `nginx/certs/portal.key` — даже для dev-smoke-test. Для локальной разработки сгенерируйте self-signed:
```cmd
docker run --rm -v %cd%/nginx/certs:/certs alpine/openssl req -x509 -nodes ^
    -newkey rsa:2048 -days 365 ^
    -keyout /certs/portal.key -out /certs/portal.crt ^
    -subj /CN=portal.company.local
```
В production используйте сертификаты от внутреннего CA, размещённые в `nginx/certs/` через volume mount или secrets.

### Docker compose: предупреждения "pull access denied"

При первом `docker compose up` вы увидите:
```
! Image portal-frontend:latest pull access denied for portal-frontend, repository does not exist
! Image portal-backend:latest  pull access denied for portal-backend, repository does not exist
```
Это **не ошибка** (`!`, не `✖`). Compose пытается pull тегов `portal-*:latest` с Docker Hub (там их нет), затем падает назад на локальный `build:`. Чтобы убрать предупреждения — `docker compose up -d --pull never` или собрать образы отдельно: `docker compose build && docker compose up -d`.

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

### Вариант 1: гибрид (быстрая итерация frontend/backend)

```bash
cp .env.example .env
# Заполнить обязательные переменные в .env (POSTGRES_PASSWORD, REDIS_PASSWORD, SECRET_KEY)

docker compose up postgres redis -d
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

### Вариант 2: full-stack smoke-test

Поднимает все 6 контейнеров (как в production):

```cmd
:: Один раз — сгенерировать self-signed TLS-сертификат
docker run --rm -v %cd%/nginx/certs:/certs alpine/openssl req -x509 -nodes ^
    -newkey rsa:2048 -days 365 ^
    -keyout /certs/portal.key -out /certs/portal.crt ^
    -subj /CN=portal.company.local

copy .env.example .env
:: Отредактировать пароли в .env

docker compose up -d --build
docker compose ps
```

Ожидаемый статус (после ~30 сек):

| Контейнер | Статус |
|---|---|
| `portal-postgres` | Up (healthy) |
| `portal-redis` | Up (healthy) |
| `portal-backend` | Up (healthy) |
| `portal-worker` | Up |
| `portal-frontend` | Up |
| `portal-nginx` | Up — порты 80/443 |

Проверка endpoints:
```bash
curl -k https://localhost/health      # 200 ok
curl -k https://localhost/ready       # 200 если DB+Redis healthy
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

---

## История блокеров и фиксов

Phase 0 проходила через 3 раунда code-review + smoke-тестов. Все ошибки задокументированы здесь, чтобы при дальнейшей работе с инфраструктурой не повторять их.

### Раунд 1 — code-review (commit `01dc8e9`)
| # | Проблема | Фикс |
|---|---------|------|
| 1 | `docker-compose build backend` без явного `target` падал | `target: production` в `docker-compose.yml` |
| 2 | Playwright не находил chromium внутри контейнера | `chown -R portal:portal /ms-playwright` в Dockerfile |
| 3 | `python-dateutil` использовался, но не был в зависимостях | добавлено в `pyproject.toml` |
| 4 | Nginx `client_max_body_size` хардкоден, не связан с `MAX_UPLOAD_SIZE_MB` | комментарий-предупреждение в `nginx.conf` |
| 5 | `package-lock.json` отсутствовал → недетерминированный CI | сгенерирован и закоммичен |
| 6 | `internal` сеть отсутствовала → backend и postgres в одной публичной сети | добавлены `internal` (internal: true) и `external` |
| 7 | `lightTheme` импорт из Naive UI падал | импорт из `naive-ui` без под-пути |
| 8 | Дубль `test-utils` в `package.json` | удалён один |
| 9 | Импорты в `scripts/create_audit_partitions.py` сломаны при запуске как модуль | исправлены на абсолютные `from app.core...` |
| 10 | ESLint 9 vs `typescript-eslint` 7 — конфликт версий | зафиксирован ESLint 8.57 + `typescript-eslint` 7.x |
| 11 | `DB_ECHO` env-переменная читалась, но не была в Settings | добавлено поле `db_echo: bool` в `config.py` |

### Раунд 2 — vue-tsc fail (commit `bacce57`)
| # | Проблема | Фикс |
|---|---------|------|
| 12 | `vue-tsc --noEmit` падал на типах Naive UI / TipTap | `skipLibCheck: true` в `tsconfig.json` |
| 13 | `import.meta.env` не типизирован → ошибка TS | `types: ["vite/client", "node"]` в `tsconfig.json` |

### Раунд 3 — smoke-test `docker compose up -d --build`
| # | Проблема | Фикс |
|---|---------|------|
| 14 | `nginx [emerg] invalid number of arguments in "add_header"` — CSP с `always;` на новой строке | CSP в одну длинную строку |
| 15 | `backend AttributeError: 'PrintLogger' object has no attribute 'name'` при первом `logger.info` | `structlog.stdlib.LoggerFactory()` вместо `PrintLoggerFactory()` |
| 16 | `nginx [emerg] cannot load certificate "/etc/nginx/certs/portal.crt"` | сгенерировать self-signed (см. раздел «Запуск локально → Вариант 2») |

### Раунд 4 — мелочи (commit `11cd615`)
| # | Проблема | Фикс |
|---|---------|------|
| 17 | Случайный `_commit_msg.txt` попал в репо | удалён, добавлен в `.gitignore` |
