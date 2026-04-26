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
1. Закоммитить или откатить текущие изменения в 7 файлах.
2. `git rm --cached` для `*.bat`, `*.ps1`, `.zenflow/`, `reset_admin.py`, `trb.md`.
3. Решение по `AGENTS.md`, `requirements.md`, `WINDOWS_CHEATSHEET.md` — оставить, переместить в `docs/internal/`, или вынести в приватный репо.
4. (Если репо станет публичным) `git filter-repo` для зачистки `trb.md` и `reset_admin.py` из истории.

### Этап 2 — закрытие открытых security-issue (0.5–1 день)
5. **P1 #33**: внедрить `_UPLOAD_MIME_ALLOWLIST` в `api/files.py::upload_files`.
6. P3 #11, #34 — закрыть или явно занести в `KNOWN_ISSUES.md` / private tracker.
7. P4 #35 — убрать `body=r.text[:300]` из error-логов `nc_federation.py`.
8. Проверить отсутствие секретов: `gitleaks detect --no-git -v`.

### Этап 3 — обязательные публичные файлы (0.5 дня)
9. Создать `README.md` (badges CI, quick start, фичи, скриншоты).
10. Добавить `LICENSE`, `SECURITY.md`, `CHANGELOG.md`.
11. Добавить `.editorconfig`.
12. Поднять `frontend/package.json::version` до `1.0.0`, добавить metadata в `backend/pyproject.toml`.
13. Удалить `backend/tests/unit/test_videos.py` (мёртвый код).

### Этап 4 — инфраструктура и CI (1 день)
14. Унифицировать `backend/Dockerfile` с `scripts/entrypoint.sh`.
15. Вынести `alembic upgrade` из entrypoint в отдельный init-step (compose `depends_on` + service `migrations`).
16. Разделить compose на `docker-compose.yml` + `docker-compose.dev.yml`.
17. Добавить в CI: `gitleaks`, `pip-audit`, `npm audit`, Trivy на образы.
18. Создать `.github/dependabot.yml`.
19. Поднять `--cov-fail-under` до 80% (после удаления test_videos.py перепроверить).

### Этап 5 — документация (1 день)
20. Сверить `docs/adr.md`, `db-schema.md`, `api-contracts.md`, `roles-matrix.md` с реальной реализацией Phase 5–8.2.
21. Создать `docs/deploy.md` (production checklist: TLS, Keycloak, Nextcloud, бэкапы, мониторинг, ротация ключей).
22. Создать или удалить `docs/phase-0.md` (на него ссылается AGENTS.md).
23. Перегенерировать `openapi.json` и приложить как артефакт релиза.

### Этап 6 — релизный коммит и тег (0.5 дня)
24. `npm audit fix` и `pip-audit` финальный прогон.
25. Полный прогон `pytest` + `npm run test:unit` + `playwright test`.
26. Smoke-test `docker compose up -d` на чистой машине по инструкции из `README.md`.
27. Тег `v1.0.0`, push, GitHub Release с приложенным CHANGELOG и openapi.json.

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
