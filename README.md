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
- 📊 **Аудит** — партиционированный по месяцам audit_log
- 🎨 **Брендинг** — логотип, фавиконка, фон логина, название портала
- ⚙️ **Системные настройки** — управление nginx-конфигом, TLS, SMTP, Keycloak
- 👥 **Управление Keycloak** — поиск/создание/блокировка/сброс пароля

---

## Стек

| Слой | Технологии |
|------|------------|
| Frontend | Vue 3 + TypeScript + Vite, Naive UI, Pinia, TanStack Query, vue-i18n, TipTap |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, ARQ, structlog |
| Хранилище | PostgreSQL 16 (hunspell_ru FTS), Redis 7 |
| Интеграции | Keycloak (OIDC), Nextcloud (WebDAV + Collabora WOPI), Postfix |
| Инфраструктура | Docker Compose, Nginx, GitHub Actions |
| Тесты | Pytest + pytest-asyncio + Testcontainers, Vitest, Playwright, k6 |

---

## Quick start

### Требования

- Docker 24+ и Docker Compose v2
- 4 GB RAM, 10 GB диска
- Поднятые **снаружи** репозитория сервисы: Keycloak, Nextcloud (с service account
  `portal-svc`), Postfix SMTP. См. [`docs/deploy.md`](./docs/deploy.md).

### Запуск

```bash
git clone https://github.com/VeryShuu/portal.git
cd portal
cp .env.example .env
# отредактировать .env: пароли, KEYCLOAK_URL, NEXTCLOUD_URL, NC_SERVICE_APP_PASSWORD, ...
docker compose up -d
```

После старта:
- UI — `https://localhost/` (или указанный `PORTAL_BASE_URL`)
- API docs — `https://localhost/api/docs`
- Healthcheck — `https://localhost/health`

Первый вход — локальным admin'ом: `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `.env`.
Сменить пароль через профиль немедленно.

---

## Документация

- [`AGENTS.md`](./AGENTS.md) — карта проекта, стек, архитектурные решения
- [`docs/adr.md`](./docs/adr.md) — Architecture Decision Records
- [`docs/db-schema.md`](./docs/db-schema.md) — схема БД (миграции 001–020)
- [`docs/api-contracts.md`](./docs/api-contracts.md) — контракты REST API
- [`docs/roles-matrix.md`](./docs/roles-matrix.md) — матрица прав
- [`docs/testing.md`](./docs/testing.md) — стратегия тестирования
- [`docs/implementation-details.md`](./docs/implementation-details.md) — детали реализации фаз
- [`docs/deploy.md`](./docs/deploy.md) — production-чеклист
- [`KNOWN_ISSUES.md`](./KNOWN_ISSUES.md) — известные нефатальные проблемы
- [`SECURITY.md`](./SECURITY.md) — политика responsible disclosure
- [`CHANGELOG.md`](./CHANGELOG.md) — история релизов

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

CI прогоняется автоматически на каждый PR — см. `.github/workflows/ci.yml`.

---

## Безопасность

Если вы нашли уязвимость — см. [`SECURITY.md`](./SECURITY.md).
**Не открывайте публичные issue с описанием уязвимостей.**

---

## Лицензия

[MIT](./LICENSE) © 2026 Reydan
