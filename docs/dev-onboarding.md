# Onboarding разработчика

> **Когда читать:** первый локальный запуск, минимальные env, тестовый пользователь.
> **Ключевой код:** `./docker-compose.dev.yml`, `./.env.example`, `./backend/app/core/config.py`.
> **ADR:** —. **См. также:** `./docs/deploy.md`, `./docs/testing.md`.

> Короткий quickstart: как поднять Portal локально, что нужно для тестов
> и какие переменные окружения минимально обязательны. Для production —
> см. [`./docs/deploy.md`](./deploy.md).

---

## 1. Требования к окружению

| Компонент | Версия | Назначение |
|-----------|--------|------------|
| Python | 3.12+ | backend, тесты |
| Node.js | 20+ | frontend, vitest, playwright |
| PostgreSQL | 16 (с расширениями `pg_trgm`, `unaccent`, `hunspell_ru`) | основная БД |
| Redis | 7 | сессии, rate-limit, ARQ |
| Docker + Compose v2 | — | удобный способ поднять всё разом |
| ruff / mypy / pytest | через `pip install -e ".[dev]"` | lint + типы + тесты |

Для backend-разработки PostgreSQL без `hunspell_ru` запустится, но `FTS`-тесты
будут падать — собирайте PG через `./postgres/Dockerfile`.

---

## 2. Быстрый старт через Docker (рекомендованный путь)

```bash
git clone https://github.com/VeryShuu/portal.git
cd portal
bash ./setup.sh        # интерактивно создаст ./.env и ./.portal-mode
# выбрать пункт "2. Разработка" в меню — поднимет dev-стенд:
#  - postgres :5432, redis :6379, backend :8000, frontend (vite) :5173
#  - hot-reload backend (uvicorn --reload), bind-mount исходников
```

После старта:
- API — http://localhost:8000/api/v1/...
- Swagger UI (напрямую) — http://localhost:8000/docs
- Frontend (Vite dev) — http://localhost:5173 (если режим dev)
- В UI — войти под `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `./.env`

---

## 3. Локальный запуск без Docker

### Backend

```bash
cd ./backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# поднять postgres + redis любым способом (например, docker run)
docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=portal -e POSTGRES_DB=portal postgres:16
docker run -d --name rd -p 6379:6379 redis:7

# минимальные env (можно положить в ./.env или ./backend/.env)
export ENVIRONMENT=development
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL="postgresql+asyncpg://postgres:portal@localhost:5432/portal"
export REDIS_URL="redis://localhost:6379/0"
export LOCAL_AUTH_ENABLED=true
export ADMIN_EMAIL=admin@example.com
export ADMIN_PASSWORD=admin12345

# миграции и старт
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

> Расширение `hunspell_ru` — собирается из `./postgres/Dockerfile`. Без
> него FTS-запросы будут возвращать ошибку при первом обращении. Для
> ручных проверок можно временно отключить FTS-маршруты или поднять
> PG через `docker compose -f ./docker-compose.yml up postgres`.

### Frontend

```bash
cd ./frontend
npm ci
npm run gen:types          # сгенерирует ./frontend/src/api/types.gen.d.ts из ./openapi.json
npm run dev                # vite — http://localhost:5173
# proxy на backend настраивается в ./frontend/vite.config.ts (по умолчанию :8000)
```

---

## 4. Минимальные env-переменные

Полный список — `./backend/app/core/config.py` (класс `Settings`).
Минимум для запуска backend:

| Переменная | Пример | Описание |
|------------|--------|----------|
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` \| `test` |
| `SECRET_KEY` | сгенерировать `secrets.token_urlsafe(48)` | сессии/CSRF, ≥ 32 символов |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/portal` | обязательно `+asyncpg` |
| `REDIS_URL` | `redis://localhost:6379/0` | сессии, rate-limit, ARQ |
| `LOCAL_AUTH_ENABLED` | `true` | разрешить `/auth/local` (для dev) |
| `ADMIN_EMAIL` | `admin@example.com` | bootstrap-админ при первом старте |
| `ADMIN_PASSWORD` | `admin12345` (≥ 8 симв.) | пароль bootstrap-админа |

Keycloak/Nextcloud/SMTP — в development не обязательны. Их параметры задаются
через Admin UI (хранятся в `./system_data/secrets/keycloak-settings.json` или в контейнере по пути `/data/secrets/keycloak-settings.json` и
`./system_data/settings/system.json` или по пути `/data/settings/system.json`).

---

## 5. Создание тестового пользователя

При первом запуске приложения (после выполнения `alembic upgrade head`) bootstrap-админ создаётся автоматически
из `ADMIN_EMAIL` / `ADMIN_PASSWORD` (в `./.env`). Дополнительных пользователей можно
завести двумя способами:

1. **Через Admin UI** — `Администрирование → Пользователи → Создать`
   (admin-роль обязательна).
2. **Через API** — `POST /api/v1/users/admin/local` с телом
   `{"email": "...", "password": "...", "full_name": "...", "role": "reader"}`,
   cookie-сессия админа обязательна.

Для интеграционных тестов фикстура `real_db_session` (см.
`./backend/tests/integration/conftest.py`) создаёт пользователей внутри
SAVEPOINT'а — данные не остаются между тестами.

---

## 6. Проверки перед PR

### Backend
```bash
cd ./backend
ruff check . && ruff format --check .
mypy app
pytest ./tests/unit ./tests/security
# integration требует реальной БД + Redis:
INTEGRATION_DB=true INTEGRATION_REDIS=true pytest ./tests/integration
```

### Frontend
```bash
cd ./frontend
npm run lint:check
npm run typecheck
npm run i18n:check
npm run test:unit
```

`gen:types` запускается автоматически в `predev` / `prebuild` /
`pretypecheck` / `pretest:unit` — отдельно вызывать не нужно.

### Полная картина CI
Workflow `./.github/workflows/ci.yml` запускает то же, что выше, плюс
`backend-integration` job со service-контейнерами postgres+redis.
Локально CI можно прогнать через [`act`](https://github.com/nektos/act)
(не обязательно).

---

## 7. Полезные ссылки

- [`./README.md`](./../README.md) — обзор стека и production-инструкция
- [`./AGENTS.md`](./../AGENTS.md) — операционный playbook (архитектура, соглашения)
- [`./docs/testing.md`](./testing.md) — стратегия тестов и команды
- [`./docs/api-contracts.md`](./api-contracts.md) — контракты REST API
- [`./docs/db-schema.md`](./db-schema.md) — схема БД
- [`./docs/roles-matrix.md`](./roles-matrix.md) — матрица ролей
