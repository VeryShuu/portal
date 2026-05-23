# Комплексное код-ревью блока «Локальная фотогалерея»

Ревью выполнено по всему стеку: backend (FastAPI + SQLAlchemy + ARQ worker) и frontend (Vue 3 + Pinia + TanStack Query), а также по сопоставлению со спецификацией `./docs/photos.md`.

---

## Выполнено

### Итерации 1–3 (B1–B18, F1–F15)
Все 33 пункта закрыты. После повторной верификации (22.05.2026):

- B1–B8, B10–B15, B17, B18 — OK
- **B9**: `storage_kind` / `storage_root` в `PhotoFolder`, ветвление по типу хранилища в `_serve_original_response`, миграция `057`, nginx-alias `/internal/photos-import/` — OK
- **B16**: `RateLimiter` + удаление on-demand генерации в `public_folder_thumbnail` (`./backend/app/api/photos/sharing.py`) — OK
- F1–F15 — OK

### Iteration 4 (закрыто)
- **Iter4 #2** PublicPhotoDTO/PublicFolderDTO — закрыто в B4 (`PhotoPublicAnon` + `PhotoListAnon`).
- **Iter4 #3** PhotoFolder.storage_kind/storage_root — закрыто в B9.
- **Iter4 #5** `photoShareUrls.ts` — закрыто (`./frontend/src/utils/photoShareUrls.ts` + использование в `useLightboxShare.ts`).
- **LightboxModal split** — код декомпозирован на `PhotoLightboxViewer.vue`, `LightboxToolbar.vue`, `SharePhotoModal.vue`, `ShareFolderModal.vue` и `LightboxTagsEditor.vue`.

### Iteration 5 (закрыто)
- **B19** Upload rate-limit приведён к спеке — `60/min` в `./backend/app/api/photos/photos.py` и в `./docs/photos.md`.
- **B20** Унифицировать формат share-URL — закрыто в F1.
- **B21** `PATCH folder` через `model_fields_set` — закрыто (`./backend/app/api/photos/folders.py`, `apply_cover_photo` принимает `None`).
- **B22** Audit event names — спека приведена к коду (формат `photos.<resource>_<action>`, таблица событий в `./docs/photos.md`).
- **F17** AVIF + `<picture><source type="image/avif">` — добавлены хелперы `thumbAvifUrl`/`publicPhotoAvifUrl`/`publicFolderAvifUrl` in `./frontend/src/api/photos.ts`; обновлены `PhotosGrid.vue`, `LightboxModal.vue`, `PhotosWidget.vue`, `PhotoTrashView.vue`, `PublicFolderPage.vue`, `PublicPhotoPage.vue`.
- **F18** Локализация `aria-labels` и захардкоженных строк во всех vue-компонентах фотогалереи (в `ru.json` и `en.json` добавлены ключи `photos.a11y.*`).
- **F19** `@keydown.space.prevent` для grid-карточек — закрыто (`PhotosGrid.vue`, `PublicFolderPage.vue`).
- **F20** `subjectSearchQuery = found.subject_name` после выбора — закрыто (`PhotoPermissionsModal.vue:195`).
- **F21** `clearTimeout(subjectSearchTimer)` в `onBeforeUnmount` — закрыто (`PhotoPermissionsModal.vue:199`).
- **F22** `clearTimeout(_tagsDebounceTimer)` в `onBeforeUnmount` — закрыто (`useLightboxPhotoTags.ts:61`).
- **F23** Единый `RECENT_LIMIT` const — закрыто (`./frontend/src/stores/photos.ts`, 4 потребителя).

---

## Предстоящие этапы

## Iteration 4 — Архитектурный рефакторинг

Цель: подготовить модуль к долгосрочной поддержке.

1. ~~**Single TrashService** — собрать soft-delete / restore / purge subtree в одном модуле; удалить дубли в `folder_service.py` / `photo_service.py` / `cleanup.py`. `L`~~ **(закрыто)**.
2. ~~**Batch ACL layer + Redis cache versioning** — `resolve_folder_permissions_batch(ids)` уже есть (B17), но без version-tag. Добавить `acl_version:{folder_id}` ключ, инвалидировать при изменении прав. `L`~~ **(закрыто)**.
3. ~~**LightboxModal split** — выделить `PhotoLightboxViewer`, `LightboxToolbar`, `SharePhotoModal`, `ShareFolderModal`, `LightboxTagsEditor` из ~700-строчного `LightboxModal.vue`~~ **(закрыто)**.
4. ~~**TanStack Query migration** — `folderTree`, `folder(id)`, `folderPhotos(id, params)`, `tags`, `photoTags(id)` через `useQuery` + invalidation. `L`~~ **(закрыто)**.

---

## Iteration 5 — Low / nice-to-have

**Backend:**
- ~~**B23.** Явные retry/timeout/idempotency для всех photo-worker задач (`process_photo_upload`, `import_scan_run`, `generate_folder_zip`, `cleanup_zip_jobs`, `detect_missing_thumbnails`)~~ **(закрыто)**.

**Frontend:**
- **F16.** Виртуализация grid (Intersection Observer / virtual list). `M` (опционально).
- ~~**F18.** Локализация aria-labels и hardcoded строк. `M`~~ **(закрыто)**.

---

## Что делать дальше — приоритизированный план

### Приоритет 1 — закрыть мелочи (S, 1 сессия)

Можно за один заход без рисков, всё локализовано:

#### B22 — Audit event names по спеке
**Где:** `./backend/app/api/photos/` (folders.py, photos.py, sharing.py, permissions.py, tags.py).
**Что делать:**
1. Открыть `./docs/photos.md`, секцию по audit-событиям (поиск `event_type` / `audit`).
2. Собрать таблицу: текущие имена в коде (`grep -rn "event_type=" ./backend/app/api/photos/`) vs ожидаемые в спеке.
3. Привести к единому формату `photos.<resource>.<action>` (`photos.folder.created`, `photos.photo.deleted`, `photos.share.created` и т. п.).
4. Если в коде встречаются нестандартные глаголы (`emptied`, `purged`), сверить со спекой и зафиксировать.
**Риск:** низкий (просто строковые литералы), но требует пересмотра потребителей audit-стрима (dashboards / reports), если есть.

#### F17 — AVIF в `<picture><source>`
**Где:** `./frontend/src/components/photos/PhotosGrid.vue`, `./frontend/src/pages/photos/PublicFolderPage.vue`, `LightboxModal.vue`, `PhotosWidget.vue`.
**Что делать:**
1. Бекенд уже отдаёт `format=avif` (см. `./backend/app/api/photos/thumbnails.py:104` и `sharing.py:409`); генерация AVIF делается параллельно с WebP (`./backend/app/services/photos_storage.py:289`).
2. В `<picture>` добавить `<source type="image/avif" :srcset="...">` перед существующим WebP-source.
3. Добавить хелпер `thumbAvifUrl(id, size)` рядом с `thumbUrl` в `./frontend/src/api/photos.ts`, передавать `?format=avif`.
4. Для public-эндпоинтов — `publicFolderAvifUrl`, `publicPhotoAvifUrl` аналогично.
**Профит:** -30…40 % трафика на современных браузерах.
**Риск:** низкий, fallback на WebP/JPEG автоматически.

#### B19 — Upload rate-limit
**Где:** `./backend/app/api/photos/photos.py` (upload endpoint) vs `./docs/photos.md`.
**Что делать:**
1. Найти текущий лимит (`grep -n RateLimiter ./backend/app/api/photos/photos.py`).
2. Сравнить со спекой; либо подтянуть код к спеке, либо обновить спеку. Чаще всего код прав, спека отстаёт — но решение требует согласования.

---

### Приоритет 2 — рефакторинг (M)

#### LightboxModal split (Iter4 #3, `M`)
**Зачем:** `LightboxModal.vue` ~700 строк, смешивает viewer / toolbar / share / tags / permissions. Тестировать и менять невозможно.

**Декомпозиция:**
```
LightboxModal.vue  (orchestrator, ~150 строк)
├── PhotoLightboxViewer.vue   (img/stage, swipe, zoom)
├── LightboxToolbar.vue       (кнопки: close, download, share, tags, prev/next)
├── SharePhotoModal.vue       (текущий share-блок для photo)
├── ShareFolderModal.vue      (текущий share-блок для folder)
└── LightboxTagsEditor.vue    (NSelect + save/cancel)
```

**Пошагово:**
1. Composables уже есть (`useLightboxView`, `useLightboxShare`, `useLightboxPhotoTags`) — каждый компонент подключает свой.
2. Сначала вытащить `SharePhotoModal` и `ShareFolderModal` — они почти изолированы, минимальные правки потребителя.
3. Затем `LightboxTagsEditor` — у него уже выделен composable.
4. `LightboxToolbar` — собирает кнопки и эмитит события.
5. `PhotoLightboxViewer` — последним: содержит больше логики (lazy load, keyboard).
6. Корневой `LightboxModal.vue` — оркестрация props / events.

**Риск:** средний. Нужна проверка focus-trap (F8), keyboard nav, aria. Покрыть e2e (Playwright) перед началом — иначе регрессии в lightbox.

#### F18 — Локализация aria + hardcoded строк (`M`)
**Где:** все vue-файлы с `aria-label="..."` без `t(...)`.
```
grep -rn 'aria-label="[А-Яа-я]\|aria-label="[A-Z]' ./frontend/src/components/photos ./frontend/src/pages/photos
```
1. Завести ключи в `./frontend/src/i18n/ru.json` под `photos.a11y.*`.
2. Заменить литералы на `:aria-label="t('photos.a11y.xxx')"`.
3. Не забыть `title`, `placeholder` если осталось.

---

### Приоритет 3 — крупный рефакторинг (L)

Делать отдельными PR'ами, каждый — самостоятельная задача с тестами.

#### Iter4 #1 — Single TrashService (`L`)
**Проблема:** soft-delete логика размазана:
- `folder_service.py` — каскадное удаление папки
- `photo_service.py` — удаление фото
- `cleanup.py` (worker) — purge по TTL
- `folders.py` (route) — `restore_folder`, `empty_trash`

**Что собрать:**
```python
class TrashService:
    async def soft_delete_folder(folder_id) -> int          # +descendants
    async def soft_delete_photo(photo_id)
    async def restore_folder(folder_id) -> int               # subtree
    async def restore_photo(photo_id)
    async def purge_folder_subtree(folder_id) -> (int, int)
    async def purge_expired(ttl_days) -> stats               # из worker
    async def list_trashed_folders(user) -> list
    async def list_trashed_photos(user, page, per_page) -> Page
```

**Шаги:**
1. Создать `./backend/app/api/photos/trash_service.py`, перенести функции; оставить тонкие route-обёртки.
2. Audit-события эмитить из одного места.
3. Покрыть unit-тестами (cascade, race, идемпотентность restore).
4. Удалить дубли из `folder_service` / `photo_service` / `cleanup`.

#### Iter4 #2 — Batch ACL + Redis version cache (`L`)
**Текущее:** `resolve_folder_permissions_batch` ходит в Redis `mget` per folder_id, но при изменении прав ничего не инвалидируется — только TTL.

**План:**
1. Ключ `photo_acl_ver:{folder_id}` (incr на каждое изменение прав).
2. Cache-key включает версию: `photo_acl:{user_id}:{folder_id}:v{N}`.
3. При `grant`/`revoke`/`move` — `INCR photo_acl_ver:{folder_id}` и для всех потомков (рекурсия по CTE).
4. Покрыть тестами: race grant→read, наследование при move.

#### Iter4 #4 — TanStack Query migration (`L`)
**Проблема:** `usePhotoListing`, `usePhotoFolderActions` дёргают API руками, кэша нет, при возврате на страницу — повторные запросы.

**Что мигрировать:**
- `folderTree` → `useFolderTreeQuery`
- `folder(id)` → `useFolderQuery(id)`
- `folderPhotos(id, params)` → `useFolderPhotosQuery(id, params)` с `keepPreviousData`
- `tags`, `photoTags(id)`
- Mutation: `useCreateFolderMutation`, `useDeleteFolderMutation`, …
- После mutation — `queryClient.invalidateQueries`.

**Уже есть пример:** `./frontend/src/queries/photos.ts` (`useMySharesQuery` и др.). Расширять по этому же паттерну.

**Риск:** средний-высокий. Перетянуть всю реактивность стора → query-кэш, удалить локальные `ref<Photo[]>`. Делать в две стадии: сначала параллельно (query + старый стор), потом удаление дублирования.

#### B23 — Retry/timeout/idempotency для photo-worker (`M`)
**Где:** `./backend/app/worker/tasks/photos/`.

Проверить каждую задачу:
| Задача | Retry | Timeout | Idempotent? |
|--------|-------|---------|-------------|
| `process_photo_upload` | ? | ? | Должна быть (проверка `processed`) |
| `import_scan_run` | ? | long | Должна (skip existing) |
| `generate_folder_zip` | ? | long | Перезапись ZIP-файла |
| `cleanup_zip_jobs` | ? | short | OK |
| `detect_missing_thumbnails` | ? | short | OK |

Привести явные `max_tries`, `job_timeout`, проверить, что повторный запуск не создаст дубль (race на upload).

---

### Когда брать F16 (виртуализация grid)
Только если реальный pain: альбомы > 1000 фото с лагами скролла. Иначе откладывать — добавляет сложность (sticky headers, lightbox-индексация ломается).

---

## Рекомендация на следующую сессию

**Берём B22 + F17 + B19** — 3 малых пункта одним PR, без миграций, без UI-регрессий. Это закроет всю Iteration 5 в backend-части и даст AVIF (видимый перф-эффект).

После этого — **LightboxModal split** как отдельный PR (готовит почву для дальнейших фич: видео в lightbox, slideshow, фильтры).

Крупные `L` (TrashService, Batch ACL, TanStack Query) — каждое отдельным PR с обязательным test coverage.
