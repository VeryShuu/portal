# Portal — корпоративный интранет-портал

Единая точка входа для сотрудников: новости, база знаний, файлы, фотогалерея,
ярлыки сервисов, уведомления. Работает только во внутренней сети / VPN.

[![CI](https://github.com/VeryShuu/portal/actions/workflows/ci.yml/badge.svg)](https://github.com/VeryShuu/portal/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## Возможности

- 🔐 **Аутентификация** — Keycloak (OIDC PKCE) + локальный fallback (email/пароль)
- 📰 **Новости** — черновики, таргетирование, FTS, версии
- 📚 **База знаний** — TipTap + Markdown, ACL, версии, экспорт PDF/DOCX/MD, vault import/export
- 🔍 **Глобальный поиск** — PostgreSQL FTS (hunspell_ru) + pg_trgm + Ctrl+K palette
- 🔗 **Ярлыки и закладки** — service links + персональные bookmarks
- 📁 **Файлы** — Nextcloud (service account) + Collabora Online
- 🖼 **Фотогалерея** — локальное хранилище, AVIF-миниатюры, share-токены, теги, ZIP-выгрузка
- 🔔 **Уведомления** — SSE-стрим, in-app + email
- 🕒 **Время в городах** — виджет на главной с настраиваемым списком городов и текущей погодой через Open-Meteo (без ключей, кэш в localStorage, обновление раз в 30 минут)
- 📊 **Аудит** — партиционированный по месяцам audit_log
- 🎨 **Брендинг** — логотип, фавиконка, фон логина, название портала
- ⚙️ **Системные настройки** — управление nginx-конфигом, TLS, SMTP, Keycloak
- 👥 **Управление Keycloak** — поиск/создание/блокировка/сброс пароля
- 🎫 **Техподдержка (Helpdesk)** — замена OTRS: заявки из веб-формы или email (IMAP-polling support-ящика), статус-машина, двусторонний email-thread, агенты, локальные вложения, архив

---

## Стек

| Слой | Технологии |
|------|------------|
| Frontend | Vue 3 + TypeScript + Vite, Naive UI, Pinia, TanStack Query, vue-i18n, TipTap |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, ARQ, structlog |
| Хранилище | PostgreSQL 16 (hunspell_ru FTS), Redis 7 |
| Интеграции | Keycloak (OIDC), Nextcloud (WebDAV + Collabora WOPI), Postfix |
| PDF/скриншоты | screenshot-service (Playwright/Chromium, отдельный контейнер) |
| Инфраструктура | Docker Compose, Nginx, GitHub Actions |
| Observability | Grafana + Loki + Prometheus + Alloy + Alertmanager (overlay `monitoring/`, ADR-044) |
| Тесты | Pytest + pytest-asyncio + Testcontainers, Vitest, Playwright, k6 |

---

## Развёртывание

### Требования

- Docker 24+ и Docker Compose v2
- 4 GB RAM, 10 GB диска
- Внешние сервисы (не входят в репозиторий): Keycloak, Nextcloud с service account `portal-svc`, Postfix SMTP.
  Подробнее — [`docs/deploy.md`](./docs/deploy.md) и [`docs/integration-keycloak-nextcloud.md`](./docs/integration-keycloak-nextcloud.md).

---

### Production

На проде **клон репозитория не нужен** — образы едут из GHCR (ADR-045), а каркас запуска (compose, .env, setup.sh, monitoring-overlay) приезжает одним tarball из GitHub Release (ADR-046).

```bash
# 1. Скачать deploy-bundle (аттачится CI к каждому релизу v*):
gh release download v1.2.3 -p 'portal-deploy-bundle-*.tar.gz'
tar xzf portal-deploy-bundle-v1.2.3.tar.gz
cd portal-deploy

# 2. Положить TLS-сертификаты (см. docs/deploy.md §5):
mkdir -p system_data/certs
cp /path/to/portal.crt system_data/certs/
cp /path/to/portal.key system_data/certs/

bash setup.sh          # → п.5 (.env, выбрать профиль "prod") → п.1 (запуск)
```

Альтернатива (если прод historical держит полный клон):
```bash
git clone https://github.com/VeryShuu/portal.git
cd portal
bash setup.sh          # создаёт папки, .env, спрашивает пароли + профиль контура
```

Режим образов задаётся в `.env` (см. ADR-045), `setup.sh` подставляет автоматически по выбранному профилю контура (ADR-046):
- **`IMAGE_PREFIX=ghcr.io/veryshuu/`** (prod-контур) — pull готовых CI-образов: `docker compose pull && docker compose up -d`.
- **`IMAGE_PREFIX=` пусто** (dev-контур) — локальная сборка из исходников: `docker compose up -d --build`.

`setup.sh` (пункт «1. Production») сам выбирает режим по `IMAGE_PREFIX` в `.env`.

**Semver-lock (ADR-047):** prod-контур обязан пиниться к релизному тегу `IMAGE_TAG=v1.x.x` в `.env` (защита от implicit-deploy — `latest` в prod-профиле отвергается). Релизный процесс для создателя:

```bash
# Из клона репо (dev-машина), на синхронизированном с origin/main HEAD:
./scripts/release.sh 1.5.0
# → CI публикует образы под тегом v1.5.0 + аттачит deploy-bundle к Release
# → на проде: IMAGE_TAG=v1.5.0 в .env → setup.sh п.6
```

Доступные теги: `gh release list --repo VeryShuu/portal`.

После старта:
- UI — `https://localhost/` (или `PORTAL_BASE_URL` из `.env`)
- API docs — `https://localhost/api/docs`
- Healthcheck — `https://localhost/health`

Первый вход: `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `.env`. **Смените пароль сразу через профиль.**
Остальные настройки (Keycloak, SMTP, TLS, лимиты) — в **Admin UI → Администрирование**.

#### Мониторинг (опционально)

Observability-стек (Grafana + Loki + Prometheus + Alloy + Alertmanager) — отдельный overlay, не входит в базовый деплой. Поднимается поверх работающего портала:

```bash
bash setup.sh          # → выбрать пункт 10 «Запустить мониторинг»
```

После старта: Grafana — `http://localhost:3001` (admin / admin, принудительная смена при первом входе). Дашборды «Portal — Logs» (централизованные логи) и «Portal — Overview» (метрики) провижн автоматически. Подробности: `docs/monitoring.md`, `monitoring/README.md`, ADR-044.

---

### Staging / тестовый стенд

Клонируйте репозиторий в отдельную папку на любом сервере и запустите через staging override:

```bash
git clone https://github.com/VeryShuu/portal.git portal-staging
cd portal-staging
bash setup.sh
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
```

Отличия от production:
- PostgreSQL и Redis доступны снаружи (5432, 6379) — для дампов и интеграционных тестов
- Backend открыт на порту 8000 (для curl/k6/ZAP)
- Nginx слушает 8080/8443 вместо 80/443
- Логирование: уровень DEBUG, JSON-формат, `ENVIRONMENT=staging`

---

### Обновление

```bash
git pull
bash setup.sh          # → пункт «6. Обновить Production»
```

Скрипт сам определяет режим по `IMAGE_PREFIX` в `.env`:
- registry (`ghcr.io/veryshuu/`) → `docker compose pull` готовых образов,
- пусто → `docker compose up -d --build` (пересборка изменившихся).

Подробно: [`docs/deploy.md`](./docs/deploy.md) §10 (включая откат через `IMAGE_TAG=sha-XXXXXXX`).

Миграции БД применяются автоматически при старте сервиса `migrations`.

---

## Документация

| Файл | Аудитория | Содержание |
|------|-----------|------------|
| [`AGENTS.md`](./AGENTS.md) | AI agent | Системный промпт, стек, архитектура, правила разработки |
| [`docs/deploy.md`](./docs/deploy.md) | DevOps / Admin | Production-чеклист, TLS, бэкапы, ротация секретов |
| [`docs/integration-keycloak-nextcloud.md`](./docs/integration-keycloak-nextcloud.md) | DevOps | Настройка Keycloak realm, mappers, NC service account |
| [`docs/api-contracts.md`](./docs/api-contracts.md) | Dev | REST API контракты всех модулей |
| [`docs/db-schema.md`](./docs/db-schema.md) | Dev | Схема БД, миграции (см. `./backend/migrations/versions/`) |
| [`docs/roles-matrix.md`](./docs/roles-matrix.md) | Dev | Матрица прав по всем модулям |
| [`docs/helpdesk.md`](./docs/helpdesk.md) | Dev | Модуль техподдержки (замена OTRS): тикеты, IMAP-ingress, статус-машина, локальные вложения, архив |
| [`docs/adr.md`](./docs/adr.md) | Dev | Architecture Decision Records (ADR-001 – ADR-047, см. также [`adr-archive.md`](./docs/adr-archive.md)) |
| [`docs/testing.md`](./docs/testing.md) | Dev / QA | Стратегия тестирования, команды, CI |
| [`SECURITY.md`](./SECURITY.md) | All | Политика responsible disclosure |
| [`openapi.json`](./openapi.json) | API consumers | OpenAPI 3.1 спецификация |

---

## Разработка

```bash
# Backend
cd backend
pip install ".[dev]"
ruff check . && ruff format --check . && mypy app
pytest tests/unit tests/security
pytest tests/integration  # требует postgres + redis

# Frontend
cd frontend
npm ci
npm run lint
npm run typecheck
npm run i18n:check
npm run test:unit
npm run test:e2e
```

CI прогоняется автоматически на каждый PR — см. [`.github/workflows/ci.yml`](./.github/workflows/ci.yml)
(jobs: backend lint, backend unit, frontend lint, frontend unit). Подробнее — [`docs/testing.md`](./docs/testing.md).

---

## Безопасность

Если вы нашли уязвимость — см. [`SECURITY.md`](./SECURITY.md).
**Не открывайте публичные issue с описанием уязвимостей.**

---

## Лицензия

[MIT](./LICENSE) © 2026 Reydan
