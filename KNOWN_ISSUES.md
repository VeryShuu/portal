# Known Issues

Список известных нефатальных проблем, не блокирующих релиз.
Источник приоритезации — внутренний security-аудит модуля Files (`trb.md`).

---

## P3 — важно, но не срочно

### #11 — Race в `grant_permission` (нет ON CONFLICT)
**Файл:** `backend/app/api/files.py` (`grant_permission`)
**Симптом:** при двух одновременных запросах с одинаковым `(folder_id, subject_id)` второй падает в HTTP 500 из-за `IntegrityError` (`UniqueConstraint`).
**Митигация:** в норме UI не позволяет дважды выдать одни и те же права; влияние ограничено.
**Фикс:** заменить SELECT+INSERT/UPDATE на `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL `insert(...).on_conflict_do_update(...)`).

### #34 — `invalidate_nc_service` использует deprecated API
**Файл:** `backend/app/services/nextcloud.py` (`invalidate_nc_service`)
**Симптом:** `asyncio.get_event_loop()` без активного loop в Python 3.12 кидает DeprecationWarning; `loop.create_task(...)` без сохранения ссылки → task может быть собран GC до завершения; `except Exception: pass` глушит ошибки закрытия httpx-клиента.
**Митигация:** функция вызывается редко — при смене настроек NC; утечка коннектов кратковременная.
**Фикс:** сделать `invalidate_nc_service` async, вызывать `await _service.aclose()` явно из endpoint `system_settings.py`.

---

## P4 — технический долг

### #12 — `subject_id` не проверяется на существование
**Файл:** `backend/app/api/files.py` (`grant_permission`)
**Симптом:** любой UUID/строку можно записать в `subject_id`; права запишутся, но не сработают (silent miss).
**Фикс:** для `subject_type="user"` валидировать `User.id`/`User.keycloak_id`; для `"group"` — лукап в Keycloak Admin API.

---

## Backlog (UX / стиль)

| # | Описание | Файл |
|---|----------|------|
| 20 | Rename папки недоступен из UI (бекенд готов) | `frontend/src/pages/FilesPage.vue`, `FileFolderNode.vue` |
| 21 | Upload: нет drag&drop и прогресс-бара | `frontend/src/pages/FilesPage.vue` |
| 22 | `children_count` всегда 0 — посчитать или убрать | `backend/app/schemas/files.py` |
| 23 | `<Teleport>` overlay вне корня шаблона | `frontend/src/pages/photos/...` |
| 24 | Emoji-иконки вместо `@vicons/ionicons5` | `frontend/src/components/FileFolderNode.vue` |
| 27 | `_parse_propfind` не различает `propstat`-статусы 200/404 | `backend/app/services/nextcloud.py` |
| 28 | `subject_id VARCHAR(255)` — поднять до 1024/Text | миграция |
| 29 | `UniqueConstraint(folder_id, subject_id)` без `subject_type` | миграция |
| 30 | `_check_module_enabled` как Depends — заменить middleware на префикс `/files/*` | `backend/app/api/files.py` |
| 31 | Циклический импорт в `open_in_collabora` | `backend/app/api/files.py` |

---

## Закрытые в текущем релизе

- **#33** — Upload MIME allow-list внедрён в `api/files.py::upload_files` (`_UPLOAD_MIME_ALLOWLIST`).
- **#35** — Логирование тел ответов NC в error-paths удалено (логируются только `status`, `ocs_statuscode`, `ocs_message[:100]`).
