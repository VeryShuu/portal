# Ревью модуля Files (Nextcloud, Phase 5)

> **Статус верификации (апрель 2026):** все заявленные правки P0/P1/P2/P3/P4 проверены
> по коду. Ниже — оставшийся технический долг и UX-замечания + новые находки (#33–#35),
> всплывшие при верификации.

### Что подтверждено по коду
- **#1 authz bypass** — `download_file/preview_file/delete_file/open_in_collabora` принимают
  только `filename`, путь склеивается из `folder.nc_path` на сервере.
- **#5 XSS preview** — `_PREVIEW_MIME_WHITELIST` (изображения + PDF) + CSP `sandbox; default-src 'none'`
  + `X-Content-Type-Options: nosniff`.
- **#4 MIME + size** — `magic.from_buffer` детектит MIME, `Content-Length` + потоковый
  счётчик с HTTP 413 при превышении `MAX_UPLOAD_SIZE_MB`. *(но — см. #33 ниже)*
- **#2/#3 path traversal** — `sanitize_name()` с whitelist-регэкспом во всех endpoint'ах.
- **#6 cleanup share** — `create_temp_public_share` возвращает `(token, share_id)`, есть
  `delete_temp_share`, вызов `delete_temp_share` в `finally` блоке `get_collabora_url_via_federation`.
- **#9 ACL soft-deleted** — `files_acl.py:166` теперь содержит `FileFolder.deleted_at.is_(None)`
  при подъёме по дереву.
- **#13 атомарность rename** — порядок `nc.move()` → `db.commit()` с компенсирующим
  `nc.move(new → old)` при ошибке коммита.
- **#7 rate-limit** — `RateLimiter(20/min)` на upload, `60/min` на download/preview.
- **#8 audit** — `files.permission_granted/revoked` и rename пишутся в audit_log.
- **#17 nc_error** — `FolderDetailResponse.nc_error: bool` выставляется при `NextcloudError`.
- **#18 Idempotency-Key** — Redis-кэш `idem:upload:{key}` с TTL 86400.
- **#10 N+1** — один `SELECT * FROM file_folders` + Python-построение дерева.
- **#19 Collabora — отменён.** Iframe-модалка удалена обратно: NC отдаёт
  `Content-Security-Policy: frame-ancestors 'self' https://collabora.mage.ru` и блокирует
  встраивание со стороны портала. Файлы открываются в новой вкладке через
  `window.open(resp.url, '_blank', 'noopener,noreferrer')`. Требование AGENTS.md про iframe
  применимо только если NC настроен с `frame-ancestors` для портального домена — в текущей
  инфраструктуре это не так.
- **#15 shared client** — `_get_shared_client()` с пулом на 20 коннектов.
- **#16 invalidate_nc_service** — вызывается из `system_settings.py:359` при смене
  `nextcloud_url`/`nc_service_app_password`. *(но — см. #34 ниже)*
- **#25 хардкод portal-svc** — `_webdav_url` использует `self._username`.
- **#26 _TIMEOUT_LIST** — 30 сек.
- **#32 Collabora-логи** — `body=r.text[:300]` убран из success-веток. *(но — см. #35 ниже)*

Все P0/P1/P2 закрыты. Ниже — оставшийся технический долг и UX-замечания.

---

## Матрица приоритетов (открытое)

| # | Проблема | Опасность | Время | Приоритет |
|---|----------|-----------|-------|-----------|
| 11 | Race в grant_permission (нет ON CONFLICT) | 🟡 Средний | 0.5 ч | **P3** |
| 33 | Upload: `detected_mime` (python-magic) не валидируется по allow-list | 🟠 Высокий | 0.5 ч | **P1** |
| 34 | `invalidate_nc_service` — fire-and-forget `loop.create_task` + `get_event_loop()` deprecated | 🟡 Средний | 0.5 ч | **P3** |
| 35 | `nc_federation.py` пишет `body=r.text[:300]` в error-логи (риск утечки токенов в общие логи) | 🟢 Низкий | 0.3 ч | **P4** |
| 12 | subject_id не проверяется на существование пользователя/группы | 🟢 Низкий | 1 ч | **P4** |
| 20 | Frontend: `updateFolder` и rename из UI недоступны | ⚪ Backlog | 1 ч | Backlog |
| 21 | Upload: нет drag&drop и прогресс-бара | ⚪ Backlog | 2–3 ч | Backlog |
| 22 | `children_count` всегда 0 — убрать или посчитать | ⚪ Backlog | 0.5 ч | Backlog |
| 23 | `<Teleport>` после закрывающего `</div>` корня | ⚪ Backlog | 5 мин | Backlog |
| 24 | Emoji-иконки вместо Naive UI icon-компонентов | ⚪ Backlog | 1–2 ч | Backlog |
| 27 | `_parse_propfind` не различает `<D:propstat>` статус 200/404 | ⚪ Backlog | 1 ч | Backlog |
| 28 | `subject_id VARCHAR(255)` — Keycloak group path может быть длиннее | ⚪ Backlog | мигр. | Backlog |
| 29 | `UniqueConstraint(folder_id, subject_id)` без `subject_type` | ⚪ Backlog | мигр. | Backlog |
| 30 | `_check_module_enabled` как `Depends` — можно заменить middleware на префикс | ⚪ Backlog | 0.5 ч | Backlog |
| 31 | Циклический импорт в `open_in_collabora` обходится локальным `import` | ⚪ Backlog | рефакт. | Backlog |

---

## 🟠 P1 — Найдено при верификации

### 33. Upload: detected_mime не сверяется с allow-list

`api/files.py::upload_files` определяет реальный MIME через `magic.from_buffer(...)`,
но **не сравнивает** его с whitelist — значение лишь подставляется как `content_type`
в `nc.upload_stream`. AGENTS.md требует «валидация MIME через python-magic», то есть
блокировку запрещённых типов. Сейчас на сервер можно залить любой бинарник, в т.ч.
исполняемые/скриптовые форматы.

**Фикс:** ввести `_UPLOAD_MIME_ALLOWLIST` (документы, изображения, архивы, видео-аудио)
и при `detected_mime not in allowlist` добавлять файл в `failed` без записи в NC.
Дополнительно — сверять `detected_mime` с расширением (`mimetypes.guess_type`) и
отклонять при сильном расхождении (например, `.docx` определяется как `application/zip`
— это допустимо, но `image/png` для `.exe` — нет).

---

## 🟡 P3 — Важно, но не срочно

### 11. Race в grant_permission

Код выполняет SELECT + update-or-insert без `SELECT FOR UPDATE`. Два параллельных запроса
с одним `(folder_id, subject_id)` оба увидят `perm_row = None` → второй упадёт
`IntegrityError` (есть `UniqueConstraint`) → клиент получит HTTP 500.

**Фикс:**
```python
from sqlalchemy.dialects.postgresql import insert
stmt = insert(FileFolderPermission).values(
    folder_id=folder_id,
    subject_type=body.subject_type,
    subject_id=body.subject_id,
    subject_name=body.subject_name,
    permission=body.permission,
    granted_by=user.id,
    created_at=datetime.now(timezone.utc),
).on_conflict_do_update(
    index_elements=["folder_id", "subject_id"],
    set_={
        "permission": body.permission,
        "subject_name": body.subject_name,
        "granted_by": user.id,
    },
).returning(FileFolderPermission)
```

---

### 34. invalidate_nc_service — некорректная очистка shared client

```python
def invalidate_nc_service() -> None:
    global _service
    import asyncio
    if _service is not None:
        try:
            loop = asyncio.get_event_loop()        # deprecated в 3.12 без running loop
            if loop.is_running():
                loop.create_task(_service.aclose())  # fire-and-forget, без awaiting
            else:
                loop.run_until_complete(_service.aclose())
        except Exception:
            pass
    _service = None
```

Проблемы:
- `asyncio.get_event_loop()` в Python 3.12 без активного loop кидает `DeprecationWarning`
  и в будущем — `RuntimeError`.
- `loop.create_task(...)` без сохранения ссылки — task может быть собран GC до завершения.
- `except Exception: pass` глушит реальные ошибки закрытия.

**Фикс:** сделать `invalidate_nc_service` async; вызвать `await _service.aclose()` явно
из endpoint `system_settings.py` (он уже async). Либо использовать
`asyncio.shield(asyncio.create_task(...))` с сохранением ссылки в модуле.

---

## 🟢 P4 — Технический долг

### 35. Логирование тел ответов NC в error-paths

`backend/app/services/nc_federation.py` в трёх местах пишет `body=r.text[:300]` при
ошибках OCS (`nc.fed_share_create_failed`, `nc.fed_share_ocs_failure`,
`nc.fed_initiator_failed`). Сейчас вызывается только при HTTP != 200, но тело может
содержать share-токен или служебные идентификаторы. Раньше эту же проблему чинили
в success-логах (#32) — стоит вынести и из error-логов.

**Фикс:** логировать только статус и `meta.statuscode`/`meta.message`, без сырого `body`.

---

### 12. subject_id не проверяется на существование

Любой UUID/строку можно записать в `subject_id` — права запишутся, но никогда не сработают.
Низкий риск (значение обычно приходит из Keycloak-данных), но облегчит отладку и снизит
количество «висячих» записей.

**Фикс:** для `subject_type="user"` проверять `select User.id where User.id = :sid OR User.keycloak_id = :sid`,
для `"group"` — лукап в Keycloak Admin API (или просто принимать на веру, если списка групп нет).

---

## ⚪ Backlog / UX и стиль

### 20. Frontend: rename папки недоступен из UI
`updateFolder` объявлен в `api/files.ts`, но кнопки rename в `FilesPage.vue` нет. Бэкенд
endpoint работает — добавить пункт меню в `FileFolderNode` и модалку.

### 21. Upload: нет drag&drop и прогресс-бара
Только `<input type="file" multiple>` + баннер «Uploading…». Для гигабайтных файлов UX слабый.
В фотогалерее DnD реализован — можно унифицировать.

### 22. `children_count`
Поле есть в `FileFolderPublic` (схема и TS-тип), но бэкенд всегда возвращает 0 (default
Pydantic). Либо посчитать `SELECT COUNT(*) ... WHERE parent_id = :id`, либо убрать поле.

### 23. `<Teleport>` overlay
Image-overlay вынесен через `<Teleport to="body">` после закрывающего `</div>` корня
шаблона. Работает, но при чтении layout сбивает.

### 24. Emoji-иконки
`fileIcon()` возвращает 📁 / 🖼️ / 📄. Не консистентно с остальным UI на Naive UI
(`@vicons/ionicons5` и пр.).

### 27. `_parse_propfind` не различает propstat-статус
Не смотрит `<D:propstat><D:status>HTTP/1.1 200 OK</D:status>` — для нестандартных свойств
может выдать пустые поля. На штатных свойствах OK, но хрупко.

### 28. `subject_id VARCHAR(255)`
Для группы Keycloak это путь типа `/IT/Backend/Senior` — в больших оргструктурах может
не хватить. Поднять до 1024 либо использовать Text.

### 29. `UniqueConstraint(folder_id, subject_id)` без `subject_type`
Семантически в индексе нужен `subject_type` тоже. Для текущих данных (UUID для user,
строка для group) коллизия маловероятна, но индекс корректнее на трёх полях.

### 30. `_check_module_enabled` как `Depends`
В каждом endpoint дублируется `dependencies=[ModuleCheck, ...]`. Чище — middleware на
префикс `/files/*`, реагирующий на `modules.json`.

### 31. Циклический импорт
В `open_in_collabora`:
```python
from app.api.system_settings import load_system_settings
from app.core.config import get_settings as _get_settings
```
Локальный import означает, что `system_settings` зависит от чего-то в `files`. Стоит вынести
загрузку `portal_base_url` в общий `app.core.config` или `app.services.url_resolver`.

---

## История закрытых проблем

P0/P1/P2 решены в коммитах модуля Files (см. changelog Phase 5). Подробности по каждому
пункту — в audit-логах и истории git.

- **P0:** #1 authz bypass, #5 XSS preview, #4 MIME + size limit
- **P1:** #2 path traversal в именах папок, #3 path traversal в именах файлов,
  #6 cleanup публичных NC-share, #9 ACL обходит soft-deleted, #13 атомарность NC move + DB
- **P2:** #7 rate-limiting, #8 audit на grant/revoke/rename, #17 nc_error флаг,
  #18 Idempotency-Key
- **P3:** #10 N+1 при дереве; #19 Collabora — оставлен `window.open` (iframe заблокирован NC CSP)
- **P4:** #15 shared httpx client, #16 invalidate_nc_service при смене настроек,
  #25 хардкод portal-svc → self._username
- **Backlog:** #14 (был ложный — TIMEOUT_DOWNLOAD=None по AGENTS.md), #26 _TIMEOUT_LIST→30s,
  #32 утечка тел ответов в логи Collabora
