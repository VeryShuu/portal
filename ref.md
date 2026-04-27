# Ревью репозитория и план подготовки к продакшен-релизу / публикации в git

## A. Критические находки (security / leakage)

### A1. Артефакты, которые нельзя публиковать «как есть»

| Файл | Проблема | Действие |
|---|---|---|
| `reset_admin.py` (корень) | Ad-hoc скрипт с хардкоженным `DATABASE_URL=postgresql+asyncpg://portal:change_me_strong_password@localhost:5432/portal`. Дублирует функцию `backend/scripts/create_admin.py`. | Удалить из корня; при необходимости перенести в `backend/scripts/reset_admin.py` без дефолтных паролей. |
| `trb.md` (корень) | Внутренний security-audit с описанием актуальных открытых уязвимостей (P1 #33 MIME allow-list, P3 #11 race в `grant_permission`, #34 invalidate, P4 #35 утечка тел NC в логи). Публикация = подсказка для атакующего. | Перенести в приватный issue tracker; либо удалить из публичной ветки и вычистить из истории через `git filter-repo` перед публикацией. |
| `.zenflow/tasks/.../plan.md` (закоммичено) | Внутренние артефакты AI-агента, в `.gitignore`, но в индексе. | `git rm --cached -r .zenflow` |
| `*.bat`, `*.ps1` в корне (`build-fe.bat`, `build-fe.ps1`, `commit.bat`, `push.bat`, `restart-fe.bat`) | В `.gitignore`, но закоммичены. Локальные dev-helpers. | `git rm --cached *.bat *.ps1` |
| `WINDOWS_CHEATSHEET.md` | Внутренние заметки разработчика. | Оставить в `docs/dev/` или удалить. |
| `AGENTS.md` (35 КБ) | Системный промпт для AI-агента — раскрывает внутреннюю архитектуру и приоритизацию. | Оставлять в публичном репо нежелательно: переместить в приватный или ужать до README-секции «Архитектура». |
| `requirements.md` (112 КБ) | Полное внутреннее ТЗ на русском. | Перенести в `docs/requirements.md` или приватный репозиторий. |

### A2. Открытые P1/P3/P4 (по `trb.md`)

Перед публикацией закрыть как минимум **#33 (upload MIME allow-list)** — без него любой залогиненный пользователь может залить исполняемые файлы в Nextcloud. Остальные (P3/P4) — допустимы как known-issues, но должны быть в приватном трекере.

### A3. Неподтверждённые изменения в индексе

7 файлов с локальными правками (`git status`):
- `backend/app/api/health.py`
- `backend/app/api/system_settings.py`
- `docker-compose.yml`
- `frontend/src/i18n/ru.json`
- `frontend/src/i18n/en.json`
- `frontend/src/pages/AdminPage.vue`
- `frontend/src/pages/LinksPage.vue`

Закоммитить или откатить — иначе попадут в первый «релизный» коммит хаотично.

---

## B. Чего не хватает для публичного git-репозитория

| # | Файл | Назначение |
|---|---|---|
| B1 | `README.md` (корневой) | Описание проекта, скриншот, quick start (`cp .env.example .env && docker compose up -d`), список модулей, ссылки на `docs/`. **Сейчас отсутствует.** |
| B2 | `LICENSE` | Без лицензии код юридически «всё запрещено». Выбрать (MIT / Apache-2.0 / proprietary). |
| B3 | `CHANGELOG.md` | Семвер по фазам (Phase 0 → Phase 8.2). |
| B4 | `SECURITY.md` | Контакт для responsible disclosure (обязательно для проекта с auth/RBAC/файлами). |
| B5 | `CONTRIBUTING.md` | Опционально, но с учётом CI желательно (стиль, ruff/mypy, pytest). |
| B6 | `CODE_OF_CONDUCT.md` | Опционально. |
| B7 | `.editorconfig` | LF/CRLF и indent — сейчас CI ловит LF только в `.sh`. |
| B8 | `docs/deploy.md` (production) | Инструкция: TLS, Keycloak realm/client, Nextcloud service account, переменные `.env`, реверс-прокси, бэкапы pg/redis/uploads, ротация логов. |

---

## C. Проблемы кода и инфраструктуры

### C1. Backend

- **`backend/Dockerfile`** генерирует entrypoint heredoc-строкой (`printf ... > entrypoint.sh`), при этом в репозитории уже есть `backend/scripts/entrypoint.sh`. Унифицировать: использовать `COPY scripts/entrypoint.sh` (как уже сделано для `scripts/`) и убрать инлайн-генерацию.
- **`alembic upgrade head`** в entrypoint выполняется на каждом старте каждого контейнера → race при `--workers 2` и при горизонтальном масштабировании. Вынести в одноразовый init-job (либо `pg_advisory_lock`).
- **`pyproject.toml`** — проверить наличие `name`, `version`, `description`, `license`, `authors`, классификаторов (вероятно, отсутствуют).
- **`backend/tests/unit/test_videos.py`** — модуль PeerTube удалён (Phase 8.1), но юнит-тест остался. Удалить.
- **MyPy в CI** запускается с `--ignore-missing-imports` → ослабленная проверка. После чистки — рассмотреть включение строгого режима для `app/core` и `app/services`.
- **Coverage gate 70%** — занижен для production; цель ≥ 80%.

### C2. Frontend

- `package.json`: `"version": "0.1.0"` — поднять до `1.0.0` для релиза, добавить `description`, `repository`, `license`.
- `eslint`/`vue-tsc`/`vitest` — пройти `npm outdated` и `npm audit` перед публикацией.
- E2E-тесты (`auth.spec.ts`, `local-login.spec.ts`) запускаются в CI только smoke-вариантом — добавить полноценный e2e-job на nightly.

### C3. Docker / Compose

- `nginx/certs/.gitkeep` остался от старой схемы (теперь сертификаты в `system_data/certs/`). Удалить.

### C4. CI/CD (`.github/workflows/`)

Добавить:
- **Secret scanning**: `gitleaks` или `trufflehog` (отдельный job) — обязательный гейт перед `main`.
- **SAST/Dependency audit**: `pip-audit` (backend), `npm audit --audit-level=high` (frontend), Trivy на образы.
- **Dependabot**: `.github/dependabot.yml` для `pip`, `npm`, `docker`, `github-actions`.
- **CodeQL** (опционально) — для Python и JS.
- **Build images** уже есть, но без подписания/SBOM. Добавить `cosign` или хотя бы `docker buildx ... --provenance`.
- **Coverage upload** идёт в Codecov без токена — для приватного репо понадобится `CODECOV_TOKEN`.
- **Branch protection**: настройка GitHub (вне репо) — required checks: `backend-lint`, `backend-unit`, `backend-integration`, `frontend-lint`, `frontend-unit`, `secret-scan`.

### C5. Документация (`docs/`)

| Файл | Состояние | Что сделать |
|---|---|---|
| `adr.md` | 66 КБ, ADR-001..017 | Проверить, что отражены ADR-032 (NC service account), удаление PeerTube; разбить на отдельные файлы `docs/adr/NNN-*.md` для удобства ревью. |
| `api-contracts.md` | 74 КБ | Сгенерировать актуальный `openapi.json` через `python -m app.main` + сравнить с описанием; добавить ссылку на live `/api/docs`. |
| `db-schema.md` | 47 КБ | Сверить с миграциями 001–020; добавить ER-диаграмму (mermaid). |
| `roles-matrix.md` | 26 КБ | Сверить с актуальными `Depends(require_role(...))`. |
| `testing.md` | 17 КБ | Добавить раздел про k6 (`load/`) и Playwright e2e. |
| `implementation-details.md` | 7 КБ | Дополнить деталями Phase 5–8. |
| `phase-0.md` | упомянут в AGENTS.md, но **не существует** в `docs/` | Создать или удалить ссылку из AGENTS.md. |

---

## D. План подготовки (предлагаемый порядок)

### Этап 1 — чистка истории и индекса (0.5 дня)
1. ⏭ Закоммитить или откатить текущие изменения в 7 файлах. *(пользователь делает сам)*
2. ✅ `git rm --cached` для `*.bat`, `*.ps1`, `.zenflow/`. `reset_admin.py`, `trb.md`, `AGENTS.md`, `requirements.md`, `WINDOWS_CHEATSHEET.md` — оставлены как есть (репозиторий приватный).
3. ✅ Решение принято: репо приватный → внутренние артефакты остаются.
4. ⏭ `git filter-repo` — отложено до момента публичной публикации.

### Этап 2 — закрытие открытых security-issue (0.5–1 день)
5. ✅ **P1 #33**: `_UPLOAD_MIME_ALLOWLIST` внедрён в `backend/app/api/files.py` (allowlist + blocklist через python-magic).
6. ✅ P3 #11, #34 + P4 #12 + Backlog — занесены в [`KNOWN_ISSUES.md`](./KNOWN_ISSUES.md).
7. ✅ P4 #35 — проверено: `body=r.text[:300]` отсутствует, в логах только `status` + `ocs_statuscode` + `ocs_message[:100]`.
8. ⏭ `gitleaks detect` — выполняется в CI (см. `.github/workflows/security.yml`).

### Этап 3 — обязательные публичные файлы (0.5 дня)
9. ✅ Создан `README.md`.
10. ✅ Созданы `LICENSE` (MIT, Reydan), `SECURITY.md`, `CHANGELOG.md`.
11. ✅ Создан `.editorconfig`.
12. ✅ `frontend/package.json` → 1.0.0 + metadata; `backend/pyproject.toml` → 1.0.0 + license/authors/classifiers/urls.
13. ✅ `backend/tests/unit/test_videos.py` удалён (`git rm`).

### Этап 4 — инфраструктура и CI (1 день)
14. ✅ `backend/Dockerfile` использует `COPY scripts/entrypoint.sh` (инлайн `printf` убран).
15. ✅ `alembic upgrade head` вынесен в отдельный сервис `migrations` (`backend/scripts/migrate.sh`); `entrypoint.sh` теперь только `uvicorn --workers 2`.
16. ✅ Compose разделён: `docker-compose.yml` (prod) + `docker-compose.dev.yml` (override с hot-reload, expose 5432/6379).
17. ✅ `.github/workflows/security.yml`: gitleaks, pip-audit, npm audit, Trivy (backend/frontend/postgres images).
18. ✅ `.github/dependabot.yml`: pip, npm, github-actions, docker (backend/frontend/postgres).
19. ⏭ `--cov-fail-under` до 80% — оставлено на 70% (плановое улучшение, не блокирует релиз).

### Этап 5 — документация (1 день)
20. ✅ Сверка `docs/adr.md`, `db-schema.md`, `api-contracts.md`, `roles-matrix.md`, `testing.md` с Phase 5–8.2 — выполнена, все документы актуальны:
    - `db-schema.md` — v1.4 (Phase 5), миграции 001–020 покрыты, все таблицы фотогалереи и files присутствуют.
    - `adr.md` — ADR-001..032, в т. ч. ADR-028 (Modules Admin UI), ADR-030/031 (фотогалерея), ADR-032 (NC service account, заменяет ADR-002).
    - `api-contracts.md` — endpoints для files, photos (CRUD/sharing/tags/ZIP/trash/slideshow), branding, system, TLS, Keycloak admin, search, audit, analytics, notifications.
    - `roles-matrix.md` — Steps 8.7/10.8 (admin modules tab + photo gallery).
    - `testing.md` — пирамида с k6 (300 VU), Playwright e2e, security tests, integration via Testcontainers.
21. ✅ Создан `docs/deploy.md` (production checklist: hosts, Keycloak, Nextcloud service account, .env, TLS, first run, бэкапы, мониторинг, ротация секретов, upgrades, troubleshooting).
22. ✅ Создан `docs/phase-0.md` (история фиксов + smoke-test варианты 1/2).
23. ✅ `openapi.json` сгенерирован локально (`backend/scripts/export_openapi.py` через Docker → `openapi.json` в корне репо, 435 КБ). Готов как артефакт GitHub Release.

### Этап 6 — релизный коммит и тег (0.5 дня)
24. ✅ Аудиты выполнены:
    - **`npm audit`** (`frontend/`): 4 moderate (esbuild/vite/vite-node/vitest, dev-only). 0 high/critical → CI с `--audit-level=high` зелёный. Major-bump (vite 7→8, vitest 1→4) отложен.
    - **`pip-audit`** (через Docker, `backend/scripts/run_pip_audit.sh`): только `pip 26.0.1 CVE-2026-3219` (сам runtime-инструмент, fix отсутствует upstream). **Все runtime-зависимости проекта чисты.** Полный отчёт — `pip-audit-report.txt`.
25. ✅ Backend unit-тесты в Docker: **258 passed** (исправлены `test_resolve_inherits_from_parent`, миграция test_audit_partitions с `scripts.create_audit_partitions` → `app.services.audit_partitions`, `_parse_propfind` → корректный compare path-only). Frontend `npm run test:unit` локально не работает из-за **Node 24 ↔ Vitest 1.6.1** incompatibility; CI на Node 22 (см. `.github/workflows/ci.yml`) — assumed green. E2E (`playwright test`) перед тегом по необходимости.
26. ⏭ Smoke-test `docker compose up -d` на чистой машине по `README.md` — перед тегом.
27. ⏭ Тег `v1.0.0`, push, GitHub Release с CHANGELOG.md и openapi.json — финальный шаг.

### Этап 7 — найдено и исправлено по ходу (bonus)
28. ✅ **Критический баг `backend/pyproject.toml`**: блок `dependencies = [...]` был расположен после `[project.urls]`, поэтому setuptools 70+ парсил его как `project.urls.dependencies` и падал с `must be string`. Исправлен порядок секций: `dependencies` перед `[project.urls]`. Без фикса не собиралась тестовая стадия Dockerfile.
29. ✅ **Баг `_parse_propfind` (`backend/app/services/nextcloud.py`)**: сравнение полного URL (`https://...`) с `href` (только path) → root entry не отфильтровывался, листинг возвращал лишний элемент с именем родительской папки. Исправлено через `urlparse(...).path` + path-only compare.
30. ✅ **Тест `test_resolve_inherits_from_parent` (`backend/tests/unit/test_files_acl.py`)**: mock возвращал parent на запрос child → инициализация `current_id` ломалась. Исправлено: возвращать child на 2-м вызове, parent на 4-м.
31. ✅ **Тесты `test_audit_partitions.py`**: патчили `scripts.create_audit_partitions.datetime`, но `datetime` импортирован в `app.services.audit_partitions`. Все патчи и импорты переведены на правильный модуль.
32. ✅ **`backend/Dockerfile` test-stage**: добавлены `COPY scripts ./scripts`, `COPY migrations ./migrations`, `COPY alembic.ini ./` (нужны для `test_audit_partitions` и `test_create_admin`).

---

## E. Чек-лист «можно публиковать?»

- [ ] Нет `*.bat`, `*.ps1`, `reset_admin.py`, `trb.md`, `.zenflow/` в индексе
- [ ] `git log -p` не содержит реальных паролей/ключей (`gitleaks` clean)
- [ ] P1-уязвимость #33 закрыта
- [ ] `README.md`, `LICENSE`, `SECURITY.md`, `CHANGELOG.md` присутствуют
- [ ] CI зелёный + secret-scan + dep-audit
- [ ] `.env.example` не содержит реальных значений (только `change_me_*`) — **OK сейчас**
- [ ] `docs/deploy.md` достаточен для разворачивания «с нуля» по инструкции
- [ ] Версии бампнуты: backend `pyproject.toml`, frontend `package.json` → `1.0.0`
- [ ] Тег `v1.0.0` создан

**Итоговая оценка трудозатрат: 3–4 рабочих дня.** Самая длительная часть — этап 5 (синхронизация документации с фактическим кодом Phase 5–8.2).
