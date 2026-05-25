# Фотогалерея — оставшиеся задачи рефакторинга

Бэклог по итогам ревью модуля «Фотогалерея». Высокоприоритетные пункты
из ревью (#3, #4, #6, #7, #10, #15, #24) и бонусы (#8, #21, перенос
репозиториев из `api/` в `services/`) уже выполнены.

**Обновление (май 2026, итерация 1):** закрыты все высокоприоритетные
пункты (B-3, F-1, F-2, F-9) и весь Doc-debt (D-1, D-2).

**Обновление (май 2026, итерация 2):** закрыт весь среднеприоритетный
кластер «надёжность под нагрузкой» — B-1, B-2, B-6, B-9, F-5, F-7, F-8.

**Обновление (май 2026, итерация 3):** закрыт весь низкоприоритетный
бэкенд-техдолг — B-4, B-5, B-7, B-8, B-10, B-11, B-12.

**Обновление (май 2026, итерация 4):** закрыт весь оставшийся фронтовый
низкоприоритетный техдолг — F-3, F-4, F-6, F-10. Бэклог пуст.

---

## Бэкенд

### ~~B-1. Дедуп thumbnail-сериализации между `thumbnails.py` и `public_views.py`~~ ✅ Выполнено (май 2026)
В `./backend/app/api/photos/_common.py` добавлен общий хелпер
`_xaccel_thumb_response(photo_id, size, fmt) -> Response | None`,
который собирает webp/avif-путь, проверяет наличие файла и возвращает
`Response(200)` с `X-Accel-Redirect` либо `None` (caller решает 404/503).
`./backend/app/api/photos/thumbnails.py` (private: 503-pending + enqueue,
семантика «no-avif» 404) и `./backend/app/api/photos/public_views.py`
(`_thumb_response()` — тонкая обёртка с 404) переиспользуют общий код.

### ~~B-2. ACL: N+1 при резолве прав в trash-листинге~~ ✅ Выполнено (май 2026)
`./backend/app/services/photos_trash.py`: оба места в
`empty_trash_for_user` и `list_trashed_photos` переведены с цикла
`resolve_folder_permission` на одиночный
`resolve_folders_permissions_batch` (один CTE на все папки +
pipelined MGET по Redis-кэшу). Контракт зафиксирован в docstring
модуля (#B-2).

### ~~B-3. Commit-границы в `TrashService`~~ ✅ Выполнено (май 2026)
Leaf-методы (`soft_delete_*`, `restore_*`, `purge_*`) больше не
вызывают `db.commit()` — коммит делает caller. Orchestrator-методы
(`purge_expired`, `empty_trash`, `empty_trash_for_user`) сохранили
per-iteration commit/rollback как batch-границу при ошибках.
Контракт зафиксирован в docstring `./backend/app/services/photos_trash.py`.
Затронуто: `./backend/app/api/photos/folders.py`,
`./backend/app/api/photos/photos.py`,
`./backend/app/worker/tasks/photos/cleanup.py`.

### ~~B-4. Унификация ответов `photo_to_public`/`folder_to_public`~~ ✅ Выполнено (май 2026)
В `./backend/app/services/photos_serializers.py` добавлен внутренний
хелпер `_resolve_folder_path(folder, folder_path)`. Сигнатуры
`photo_to_public` и `photo_to_public_anon` теперь принимают
опциональный ORM-объект `folder: PhotoFolder | None` вторым позиционным
аргументом; legacy-параметр `folder_path` оставлен keyword-only для
обратной совместимости. Все вызывающие места упрощены — паттерн
`_photo_to_public(photo, folder_path=folder.path if folder else None)`
заменён на `_photo_to_public(photo, folder)`. Затронуто:
`./backend/app/api/photos/photos.py`,
`./backend/app/api/photos/photo_service.py`,
`./backend/app/services/photos_trash.py`.

### ~~B-5. Storage-stats: вынести SQL-агрегацию из эндпойнта~~ ✅ Выполнено (май 2026)
В `./backend/app/services/photos_photo_repo.py` добавлен
`fetch_storage_stats(db, *, top_limit=50) -> dict`, который собирает
ответ для `GET /api/v1/photos/storage-stats` из существующих хелперов
(`fetch_storage_stats_top_folders` + `fetch_global_storage_totals`).
Эндпойнт-оркестратор `get_storage_stats` в
`./backend/app/api/photos/photo_service.py` свёлся к одному вызову
репозитория — никакого SQL в api-слое не осталось.

### ~~B-6. Tests: integration-тест на realtime `photo_processed`~~ ✅ Выполнено (май 2026)
В `./backend/tests/unit/test_notifications.py` добавлен
`test_publish_photo_processed_emits_sse_event_b6`, который запускает
полный pipeline «`publish_photo_processed` → Redis-стрим
`notifications:photos` → `_sse_generator` → SSE-frame». Проверяет
`event: photo_processed`, наличие `photo_id`/`folder_id` в payload
и Last-Event-ID композит `personal|meetings|photos`. Закрывает «слепое
пятно» между ранее изолированными тестами publish и SSE.

### ~~B-7. Tests: cron `detect_missing_thumbnails`~~ ✅ Выполнено (май 2026)
В `./backend/tests/unit/test_worker_photos_tasks.py` добавлены
`TestDetectMissingThumbnails::test_skips_when_thumb_present` (фото
с готовым 200.webp на диске не реквьюится),
`test_resets_processed_flag_when_thumb_missing` (рассинхрон БД↔диск
сбрасывает `processed=false` и реквьюит),
`test_no_redis_pool_short_circuits` (без redis-pool — no-op).

### ~~B-8. Tests: `cleanup_zip_jobs` и `cleanup_deleted_photos`~~ ✅ Выполнено (май 2026)
В `./backend/tests/unit/test_worker_photos_tasks.py` добавлены
`TestCleanupZipJobs::test_missing_file_does_not_raise` (TTL-боундари —
запись истекла, но файла уже нет → не падает),
`TestCleanupZipJobs::test_filter_uses_expires_at_cutoff` (SQL-фильтр
проверяет `expires_at`-граничник),
`TestCleanupDeletedPhotos::test_ttl_days_boundary_is_30` (фиксируем
константу TTL=30 для `purge_expired`).

### ~~B-9. import_scan: транзакционная гранулярность~~ ✅ Выполнено (май 2026)
`_flush_batch()` в `./backend/app/worker/tasks/photos/import_scan.py`
теперь оборачивает `db.add(p)` + `db.flush([p])` для каждого фото
в собственный SAVEPOINT (`async with db.begin_nested()`). Ошибка
на N-м файле (UNIQUE/DataError) откатывает только этот файл —
остальной батч продолжает работать; падение логируется как
`photos.import.flush_failed` и попадает в `errors[]`.

### ~~B-10. Sharing: TTL-валидация~~ ✅ Выполнено (май 2026)
В `PhotosModuleSettings` (`./backend/app/core/modules_config.py`)
добавлено поле `max_share_ttl_days: int = Field(default=365, ge=1, le=365)`
с runtime-капой. Прокинуто через `PhotosModuleOut`/`PhotosModuleIn`/
`_photos_out` в `./backend/app/api/modules.py` и `update_photos_module`.
В `./backend/app/api/photos/sharing.py` добавлен хелпер
`_validate_share_ttl(redis, requested_days)`, который вызывается из
`create_share_link` (`POST /{photo_id}/share`) и `create_folder_share`
(`POST /folders/{folder_id}/share`) — превышение runtime-капы
возвращает HTTP 400. Pydantic-капа `le=365` на `expires_in_days`
осталась как абсолютный потолок.

### ~~B-11. Аудит: `permission_granted` без diff~~ ✅ Выполнено (май 2026)
В `./backend/app/api/photos/permissions.py::grant_folder_permission`
теперь до перезаписи `perm.permission` сохраняется
`previous_permission: str | None` (для апдейта — старый уровень,
для нового гранта — `None`, аналогично в IntegrityError-ветке).
Поле прокидывается в `metadata` события `photos.permission_granted`
рядом с `permission` и `subject_id`.

### ~~B-12. Логи: единый префикс `photos.*`~~ ✅ Выполнено (май 2026)
Переименованы оставшиеся события без префикса `photos.`:
`keycloak.search_failed` → `photos.keycloak.search_failed`
(`./backend/app/api/photos/permissions.py`),
`photos_acl.invalidate_failed` → `photos.acl.invalidate_failed`
(`./backend/app/services/photos_acl.py`). Прочие неймспейсы
(`photos.upload.*`, `photos.zip.*`, `photos.thumbnail.*`,
`photos.import.*`, `photos.detect_missing.*`) уже соответствовали
конвенции.

---

## Фронтенд

### ~~F-1. Дедупликация lightbox между `PhotosIndexPage`/`PublicFolderPage`~~ ✅ Выполнено (май 2026)
Создан `./frontend/src/components/photos/LightboxBase.vue` с общей
оболочкой (close/prev/next/wheel/keyboard, восстановление фокуса,
focus-trap). `./frontend/src/components/photos/LightboxModal.vue` и
`./frontend/src/pages/photos/PublicFolderPage.vue` переведены на
базу со слотами для stage/toolbar/info. `PublicPhotoPage.vue` —
standalone single-photo view, навигации нет, миграция не нужна.

### ~~F-2. Типы из openapi: `Photo.blurhash`~~ ✅ Выполнено (май 2026)
`./openapi.json` и `./frontend/src/api/types.gen.d.ts` пересобраны
(`blurhash?: string | null`). `PhotosGridBase.vue` сделан generic
(`<script setup lang="ts" generic="T extends { id: string }">`),
ручные `as Photo`-касты убраны из `PhotosGrid.vue`,
`PhotoTrashView.vue`, `PublicFolderPage.vue`. `vue-tsc --noEmit`
зелёный.

### ~~F-3. Типы для `blurhash` npm-пакета~~ ✅ Выполнено (май 2026)
Пакет `blurhash@2.0.5` ships с собственным
`./frontend/node_modules/blurhash/dist/index.d.ts` (объявляет `decode`,
`encode`, `isBlurhashValid`). `vue-tsc --noEmit` зелёный — отдельный
shim или `@types/blurhash` не нужны, описание задачи устарело.

### ~~F-4. `useLightboxView` — добавить тесты на rotate/zoom-границы~~ ✅ Выполнено (май 2026)
В `./frontend/tests/unit/use-lightbox-view.spec.ts` добавлены 9 тестов:
- initial state (`zoom=1`, `rotation=0`, `imgStyle.transform`),
- кап `zoomIn` на 8 и пол `zoomOut` на 0.25,
- шаг `0.25` с округлением до 2 знаков,
- `rotateLeft`/`rotateRight` по 90° с modulo 360,
- `resetView` восстанавливает дефолты,
- `imgStyle` отражает текущие `zoom`/`rotation`,
- `onLightboxWheel` с `deltaY<0`/`deltaY>0` вызывает `zoomIn`/`zoomOut`.

### ~~F-5. `PhotoThumb`: повторный paint blurhash при кэш-хите~~ ✅ Выполнено (май 2026)
В `./frontend/src/components/photos/PhotoThumb.vue` добавлены
модульная `Map<string, Uint8ClampedArray>` (`_blurhashCache`,
cap `_BLUR_CACHE_MAX = 100`) и хелпер `_cachedDecode(hash, w, h)`.
Используем insertion-order JS Map как дешёвый LRU (delete+set на hit,
drop самого старого ключа при переполнении). `paintBlurhash()` теперь
читает из кэша вместо повторного `decodeBlurhash` при каждом watch.

### ~~F-6. Подсветка drop-zone при выборе папки без прав~~ ✅ Выполнено (май 2026)
В `./frontend/src/components/photos/PhotosGrid.vue` добавлен
`watch(() => props.canUpload, ...)`: при переключении папки во время
drag, если `canUpload` становится `false` и `isDraggingOver=true`,
компонент эмитит `drag-leave` — родитель сбрасывает state, подсветка
исчезает реактивно без ожидания `dragleave` от браузера.

### ~~F-7. `usePhotoListing.ts`: debounce-таймер протекает на unmount~~ ✅ Выполнено (май 2026)
`./frontend/src/composables/usePhotoListing.ts` очищает
`_refetchTimer` через `clearTimeout` в `onBeforeUnmount`.

### ~~F-8. SSE re-connect: ретрай-стратегия~~ ✅ Выполнено (май 2026)
`./frontend/src/stores/notifications.ts` использует экспоненциальный
backoff с потолком: `Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt,
RECONNECT_MAX_MS)`. Защищает бэк от лавины SSE-реконнектов при кратких
сетевых сбоях.

### ~~F-9. A11y: focus-trap в lightbox~~ ✅ Выполнено (май 2026)
Focus-trap реализован внутри `LightboxBase.vue` (handleTab + save/restore
previouslyFocusedElement). Покрывает оба потребителя (`LightboxModal.vue`
и `PublicFolderPage.vue`) автоматически. Дополнительная зависимость
от пакета `focus-trap` не понадобилась.

### ~~F-10. i18n: ключи `photos.trash.*` без английского варианта~~ ✅ Выполнено (май 2026)
Проверка показала: `./frontend/src/i18n/en.json` содержит ветку
`photos.trash` полностью — по deep-diff с `./frontend/src/i18n/ru.json`
недостающих ключей под `photos.trash.*` нет. Описание задачи устарело
(локали хранятся в одном файле `en.json`/`ru.json`, а не в
`locales/en/photos.json`).

---

## Doc-debt

### ~~D-1. ADR-031: обновить под cron-самоисцеление и пред-commit enqueue~~ ✅ Выполнено (май 2026)
В `./docs/adr.md` к ADR-031 добавлено дополнение (пункты 7–8):
описаны cron `detect_missing_thumbnails` (самоисцеление БД↔диск) и
инвариант enqueue-после-commit для `import_scan` и `POST /upload` (#15).

### ~~D-2. `./docs/photos.md` §10 (тесты) — добавить новые smoke-кейсы~~ ✅ Выполнено (май 2026)
В `./docs/photos.md` §9 (тесты — секция была перенумерована) добавлены
упоминания backend-тестов на leaf/orchestrator-методы `TrashService`
после #7/#B-3 и фронтового `photos-components-smoke.spec.ts` после
унификации #F-1.

---

## Что осталось сделать

Бэклог пуст. Все пункты ревью «Фотогалерея» закрыты по итогам
четырёх итераций (май 2026).

### Закрытые пункты (для истории)
- **Бэкенд:** B-1, B-2, B-3, B-4, B-5, B-6, B-7, B-8, B-9, B-10, B-11, B-12.
- **Фронтенд:** F-1, F-2, F-3, F-4, F-5, F-6, F-7, F-8, F-9, F-10.
- **Doc-debt:** D-1, D-2.
