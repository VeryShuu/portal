# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/), [SemVer](https://semver.org/).

## [Unreleased]

### Added
- `_UPLOAD_MIME_ALLOWLIST` в `api/files.py::upload_files` — explicit allow-list
  для загрузок в Nextcloud (closes trb #33).
- `KNOWN_ISSUES.md` — реестр known issues (P3/P4/Backlog).
- `LICENSE` (MIT), `README.md`, `SECURITY.md`, `.editorconfig`.

### Changed
- Bump backend/frontend metadata: `version 1.0.0`, добавлены `description`,
  `license`, `repository`.

### Removed
- `backend/tests/unit/test_videos.py` — модуль PeerTube удалён в Phase 8.1.
- Закоммиченные dev-helper скрипты (`*.bat`, `*.ps1`) и `.zenflow/` —
  убраны из индекса (остаются игнорируемыми).

---

## [1.0.0] — 2026-04 — релиз первой версии

Готовый к продакшену набор модулей; все Phase 0–8.2 завершены.

### Phase 8.2 — Управление Keycloak
- Поиск/создание/блокировка/сброс пароля пользователей через Keycloak Admin API
  (`app/api/keycloak_admin.py`).

### Phase 8.1 — Видео (iframe embed)
- PeerTube полностью удалён.
- Видео встраиваются как iframe через TipTap-расширение `IframeEmbed.ts` в KB-редакторе
  и новостях.

### Phase 8 — Брендинг + системные настройки
- `app/api/branding.py` — логотип, фавиконка, фон логина, название/описание портала.
- `app/api/system_settings.py` — управление nginx-конфигом, TLS, SMTP, Keycloak URL.
- `app/api/modules.py` — вкл/откл модулей (photos, nextcloud).
- `stores/branding.ts`. Хранение: `/data/branding/` + `/data/settings/`.

### Phase 7 — Фотогалерея
- Локальное хранилище `/data/photos/`, AVIF-миниатюры (3 размера).
- ACL-папки (viewer/uploader/manager), share-токены (приватные + публичные папки).
- Теги, ZIP-выгрузка (ARQ), bulk-операции, корзина, slideshow, DnD-загрузка, QR-код.
- Миграции 014–019.

### Phase 6 — Audit + Analytics
- `audit_log` партиционирована по месяцам (миграция 013).
- ARQ batch flush каждые 2 сек.

### Phase 5 — Nextcloud files
- Service account `portal-svc` (ADR-032), WebDAV + Collabora OCS.
- `file_folders` + `file_folder_permissions` (миграция 020).
- 13 endpoints, 30+ unit-тестов.

### Phase 4 — Уведомления
- `notifications` (миграция 012), SSE-стрим, Redis Streams.
- Keepalive + connection limit per user.

### Phase 3.5 — KB Markdown + Obsidian-совместимость
- Media-uploads, attachments, vault export/import (.zip), MD export, diff между версиями.

### Phase 3 — KB + Search
- `kb_*` (миграции 008–010), ACL по разделам/статьям.
- TipTap+Markdown, версии, комментарии, suggestions, feedback.
- Экспорт PDF (Playwright)/DOCX (python-docx).
- Глобальный поиск (FTS hunspell + pg_trgm fallback + typeahead), Ctrl+K palette.

### Phase 2.1 — Локальная аутентификация
- Bootstrap admin из env, `/auth/local/login`, bcrypt.
- Account-linking при первом Keycloak-логине.

### Phase 2 — Links + Bookmarks
- service_links CRUD + SSO-проброс, bookmarks CRUD + reorder.

### Phase 1 — Auth + Users + News
- Keycloak OIDC PKCE, Redis-сессии, upsert пользователей из JWT.
- Новости CRUD + версии + FTS + ARQ cron.

### Phase 0 — Инфраструктура
- Docker Compose, postgres+hunspell, backend skeleton, nginx, migrations, CI/CD.
