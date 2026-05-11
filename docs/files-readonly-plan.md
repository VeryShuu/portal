# Read-only режим для пользователей с правом `viewer`

## Цель

Сейчас пользователь с правом `viewer` на папку:

- не видит кнопки «Удалить» и UI загрузки (это работает корректно — `./frontend/src/stores/files.ts` `canUpload`/`canManage`);
- **но** видит ту же кнопку «Редактировать» и при клике открывает Collabora в полноценном режиме записи и может сохранить изменения, сделать экспорт, переименовать и т. п.

Задача — обеспечить, чтобы:

1. У `viewer` кнопка называлась «Посмотреть», а не «Редактировать»;
2. При открытии файл уходил в Collabora в режиме **read-only** (без возможности сохранить, экспортировать новую версию или иначе записать в файл);
3. Серверная защита была настоящей: даже прямой вызов API не должен позволить запись.

Альтернатива «свой просмотрщик xlsx/docx без Collabora» — отвергнута: плохой рендер, большой бандл, дублирование функционала. Collabora уже умеет в WOPI read-only — используем это.

---

## Архитектура

Текущая логика открытия:

1. `POST /files/open` (`./backend/app/api/files/upload.py:227`) проверяет `viewer` и зовёт `CollaboraClient.get_collabora_url_via_federation()` либо `get_collabora_url()`.
2. Federation flow (`./backend/app/services/nc_federation.py:101` `create_temp_public_share`) создаёт публичный шаринг в Nextcloud с `permissions=3` (read + update). Полученный share-токен передаётся в Collabora через richdocuments-инициатор.
3. Nextcloud при открытии WOPI-сессии передаёт Collabora `UserCanWrite` исходя из `permissions` шары.

**Ключевой рычаг**: при создании публичной шары менять `permissions` на `1` (read-only) для пользователей без права `editor`. Это включает настоящий read-only на стороне WOPI/Collabora, обойти его с фронта невозможно.

---

## Бэкенд

### B1. Расчёт флага `can_write` в `open_in_collabora`

Файл: `./backend/app/api/files/upload.py` (функция `open_in_collabora`, строки ~227–274).

Сейчас:

```python
perm = await resolve_folder_permission(user, folder, db, redis)
if not perm_gte(perm, "viewer"):
    raise HTTPException(status_code=403, detail="Insufficient file permissions")
```

Добавить:

```python
can_write = perm_gte(perm, "editor")
```

И прокинуть в оба вызова:

```python
data = await nc.get_collabora_url_via_federation(
    file_nc_path=nc_path,
    portal_base_url=portal_base_url,
    redis=redis,
    user_id=str(user.id),
    display_name=display_name,
    avatar=avatar,
    can_write=can_write,
)
# ...
data = await nc.get_collabora_url(nc_path, display_name, can_write=can_write)
```

В ответ `FileOpenResponse` добавить поле `can_write: bool`, чтобы фронт мог отрисовать индикатор «Read-only» в шапке таба, если потребуется.

### B2. Расширение схемы `FileOpenResponse`

Файл: `./backend/app/schemas/files.py` — добавить:

```python
class FileOpenResponse(BaseModel):
    type: Literal["collabora"]
    url: str
    display_name: str
    can_write: bool = True  # default для обратной совместимости
```

### B3. Сервис `CollaboraClient` — проброс `can_write`

Файл: `./backend/app/services/nextcloud/collabora.py`.

#### B3.1 `get_collabora_url_via_federation`

Добавить параметр `can_write: bool = True` и передать его в `create_temp_public_share`:

```python
share_token, share_id = await fed.create_temp_public_share(
    nc_url=webdav._nc_url,
    basic_auth=webdav._basic_auth,
    nc_relative_path=nc_relative,
    can_write=can_write,
)
```

В fallback на legacy путь (`return await self.get_collabora_url(...)`) тоже передать `can_write`.

#### B3.2 `get_collabora_url` (legacy fallback)

Принять `can_write: bool = True`. В `_try_richdocuments_ocs` добавить параметр:

```python
params={"format": "json", "fileId": file_id, "permission": "edit" if can_write else "readonly"}
```

(Параметр `permission` поддерживается richdocuments OCS endpoint; если версия NC игнорирует — это допустимо, потому что основной путь у нас federation.)

В `_try_direct_editing` добавить:

```python
params={
    "format": "json",
    "path": nc_path,
    "editorId": "richdocuments",
    "fileType": "openWith" if can_write else "view",  # см. NC API
}
```

(Если NC версия не поддерживает — оставить как есть, fallback редко используется.)

### B4. Главное место — `create_temp_public_share`

Файл: `./backend/app/services/nc_federation.py` (функция начинается на строке 101).

Изменить сигнатуру и тело:

```python
async def create_temp_public_share(
    *,
    nc_url: str,
    basic_auth: str,
    nc_relative_path: str,
    hours: int = 2,
    can_write: bool = True,
) -> tuple[str, int]:
    ...
    data = {
        "path": nc_relative_path,
        "shareType": "3",
        "permissions": "3" if can_write else "1",  # 3 = read+update, 1 = read-only
        "expireDate": expire_at,
    }
```

Это и есть та строка, которая физически выключает запись в Collabora.

### B5. Аудит-эвент

В `./backend/app/api/files/upload.py` — добавить флаг в audit:

```python
metadata={"folder_id": str(folder.id), "can_write": can_write}
```

Тип эвента можно оставить общим `files.file_opened_collabora`, либо ввести отдельный `files.file_opened_collabora_readonly` — на усмотрение, для аналитики удобнее булев флаг в metadata.

### B6. Аудит ACL по write-эндпоинтам (защита от прямых вызовов API)

Сейчас в `./backend/app/api/files/files_ops.py` и `./backend/app/api/files/upload.py` уже стоит `require_folder_permission(..., "editor", ...)` на upload/move/rename/delete. Нужно явно пройтись и подтвердить, что **на каждом write-эндпоинте есть `editor`-чек**:

| Эндпоинт | Файл | Текущая проверка | Должна быть |
|---|---|---|---|
| `POST /files/folders/{id}/upload` | `upload.py:59` | `editor` | ок |
| `DELETE /files/folders/{id}/files/{name}` | `files_ops.py:46` | `editor` | ок |
| `PATCH /files/folders/{id}/files/{name}` (rename) | `files_ops.py:141` | `editor` | ок |
| `POST /files/folders/{id}/files/{name}/move` | `files_ops.py:255-256` | `editor` (src + target) | ок |
| `POST /files/open` | `upload.py:236` | `viewer` | ок (запись блокируется через WOPI) |
| `POST /files/folders` (create) | `folders.py:139` | `editor` родителя | ок |
| `PATCH /files/folders/{id}` | `folders.py:225` | `manager` | ок |
| `DELETE /files/folders/{id}` | `folders.py:296` | `manager` | ок |
| Permissions CRUD | `permissions.py` | `manager` | ок |

Действие: написать **тесты** (см. раздел «Тесты»), которые от имени `viewer` бьют по всем write-эндпоинтам и ждут 403.

### B7. Federation initiator — display name + permissions

Federation flow и так создаёт временный share от имени системного пользователя, и Collabora через WOPI получит `UserCanWrite=false` именно из `permissions=1` шары. Менять `nc_federation.request_initiator_direct_url` не нужно — там не передаётся уровень прав, NC сам резолвит из шары.

---

## Фронтенд

### F1. Тип ответа `openInCollabora`

Файл: `./frontend/src/api/files.ts` — добавить `can_write: boolean` в тип ответа (соответственно регенерировать `./frontend/src/api/types.gen.d.ts` или дописать вручную, как принято в проекте).

### F2. Геттер `canEdit` в files store

Файл: `./frontend/src/stores/files.ts`. Сейчас есть `canUpload` и `canManage`. Семантически `canUpload === canEdit` (оба требуют `editor`+), но имена разные. Для ясности добавить алиас:

```ts
const canEdit = computed(() => {
  const p = currentFolder.value?.permission
  return p === 'editor' || p === 'manager' || auth.isAdmin
})
```

И экспортировать `canEdit` рядом с `canUpload`. Альтернатива — переиспользовать `canUpload`, но `canEdit` читабельнее в контексте кнопки.

### F3. Кнопка в `FilesTable.vue` — название и тип

Файл: `./frontend/src/components/files/FilesTable.vue` (строка ~148).

Сейчас:

```ts
}, { default: () => t('files.edit') })
```

Изменения:

1. Добавить prop `canEdit: boolean` (передавать из `FilesPage.vue` — `:can-edit="store.canEdit"`).
2. Логика лейбла:

```ts
const label = props.canEdit ? t('files.edit') : t('files.view')
```

3. Иконка/тип кнопки: для read-only сделать `type: 'default'` и `ghost: false` (или другой стиль), чтобы визуально отличалось от записи. По желанию — `<EyeOutline>` иконка вместо `<EditOutline>`.

4. Кнопка должна показываться **всегда** для офисных файлов (xlsx/docx/odt/pptx и т. д.), независимо от `canEdit` — она и есть единственный способ их посмотреть. Сейчас, судя по коду, она внутри ветки, которая возможно скрыта по `canUpload`. Это надо проверить и убрать зависимость от `canUpload` для самой кнопки открытия Collabora.

### F4. Передача из `FilesPage.vue`

Файл: `./frontend/src/pages/FilesPage.vue`. Добавить во все три места, где монтируется `FilesTable`:

```vue
:can-edit="store.canEdit"
```

### F5. i18n

Файлы:

- `./frontend/src/i18n/ru.json` — добавить ключ:

```json
"files": {
  ...
  "edit": "Редактировать",
  "view": "Посмотреть",
  ...
}
```

(Корневой блок `"files": {}` — около строки 1374 в текущем `ru.json`.)

- `./frontend/src/i18n/en.json` — `"view": "View"`.

### F6. Бейдж «Только чтение» в шапке (опционально, но желательно)

В `./frontend/src/components/files/FilesToolbar.vue` или над таблицей — небольшой бейдж/тег, если `!store.canEdit && store.currentFolder`:

```vue
<NTag v-if="!canEdit" size="small" type="info">{{ t('files.readonly') }}</NTag>
```

С i18n-ключом `"files.readonly": "Только чтение"` / `"Read-only"`.

### F7. Другие места, где возможна запись

Проверить и при необходимости скрыть/задизейблить для `viewer`:

- кнопка «Создать папку» (требует `editor` родителя — уже скрыта через `canUpload`/`canManage`, перепроверить);
- D&D зона (`FilesDropZone`) — уже завязана на `store.canUpload`;
- bulk-операции (`FilesBulkBar`) — то же;
- контекстные меню в `FilesTable` (move, rename) — должны прятаться по `canEdit`.

---

## Тесты

### T1. Backend — pytest

Файл: новый `./backend/tests/files/test_readonly.py`.

Кейсы:

1. **Viewer открывает Collabora → ответ 200, `can_write=False`, в NC создаётся share с `permissions=1`.** Замокать `httpx`-вызов к NC, проверить body.
2. **Editor открывает → `can_write=True`, share с `permissions=3`.**
3. **Viewer пытается DELETE/PATCH/upload/move → 403** на каждом write-эндпоинте.
4. **Manager корневой папки + viewer на под-папке** — ACL-резолюшен через CTE: проверить, что дочерний viewer не апгрейдится до edit от родителя (он уже работает по best-perm — наоборот, проверить, что родительский manager даёт manager на дочерней).
5. **Admin** — всегда `can_write=True`.

### T2. E2E — playwright

Файл: добавить кейсы в `./frontend/tests/` (если есть e2e-набор) либо в существующий files-spec.

1. Залогиниться как `viewer`-пользователь, открыть папку с xlsx, увидеть кнопку «Посмотреть», кликнуть — открывается новая вкладка, URL содержит токен read-only шары (или просто проверить, что вкладка открылась).
2. Залогиниться как `editor`, увидеть кнопку «Редактировать».
3. Кнопок «Удалить», «Загрузить», «Создать папку» у `viewer` нет.

### T3. Ручная проверка в Collabora

Открыть xlsx как `viewer`, убедиться, что:

- меню «Файл → Сохранить» неактивно или сохранение даёт ошибку;
- редактирование ячеек заблокировано (или Collabora показывает баннер «Read-only»);
- экспорт/печать может остаться доступен (это нормально для read-only режима);
- закрытие/повторное открытие как `editor` снова разрешает запись.

---

## Миграция / откат

- Изменения **обратно совместимы**: `can_write` имеет дефолт `True`, старые клиенты получат прежнее поведение.
- Миграции БД не требуются — `permission` уже хранится, новых полей нет.
- Откат: revert PR. Активные read-only сессии в Collabora просто истекут вместе с временной шарой (TTL 2 часа + 1 день, как сейчас).

---

## Чек-лист имплементации

- [ ] B2: `FileOpenResponse.can_write` добавлен.
- [ ] B4: `create_temp_public_share` принимает `can_write`, выставляет `permissions`.
- [ ] B3: `CollaboraClient` пробрасывает `can_write` в federation и legacy.
- [ ] B1: `open_in_collabora` вычисляет `can_write` и передаёт в сервис.
- [ ] B5: audit metadata содержит `can_write`.
- [ ] B6: тесты на 403 для viewer на всех write-эндпоинтах.
- [ ] F1: тип ответа дополнен.
- [ ] F2: `canEdit` геттер в store.
- [ ] F5: i18n-ключ `files.view` (RU + EN).
- [ ] F3: лейбл и стиль кнопки переключаются по `canEdit`.
- [ ] F4: prop `canEdit` пробрасывается из `FilesPage`.
- [ ] F6: бейдж «Только чтение» (опционально).
- [ ] T1: pytest зелёный.
- [ ] T2: e2e зелёный.
- [ ] T3: ручная проверка в Collabora пройдена.
